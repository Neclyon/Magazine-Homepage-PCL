"""AXAML 导出模块：构建出的 WPF 主页顺带产出 PCL-CE 能直接加载的 AXAML。

HomepageBuilder 的工程模块即插件，这里监听 project.genxaml.return，拿最终 XAML 文本
做一次方言转换，写到环境变量 MAGAZINE_AXAML_OUT 指定的位置（main.py 设成
output/Custom.axaml）。原 Custom.xaml 原封不动留给原版 PCL。

转换只覆盖本工程实际会生成的构造，不是通用 WPF→AXAML 翻译器：
  * 样式块整体丢弃，改成内嵌的 Avalonia 样式 + 逐元素展开的等效属性
  * FlowDocument/Paragraph/List/ListItem → TextBlock + Inlines，列表项手加圆点
  * Trigger/MultiDataTrigger → Selector 伪类（写在内嵌样式里）
  * Line → 细 Border；ImageBrush/Image → pclcontrols:MyImage
  * pack:// 资源 → avares://PCL.Launcher/Assets/...；ToolTip → ToolTip.Tip
  * 图标 SVG 路径挪进 sys:String 资源（校验器不接受 Logo 直接写路径数据）
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from homepagebuilder.interfaces.Events import on

XAML_NS = "http://schemas.microsoft.com/winfx/2006/xaml"
X_NS = "{" + XAML_NS + "}"

ROOT_OPEN = (
    '<StackPanel xmlns="https://github.com/avaloniaui"\n'
    '            xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"\n'
    '            xmlns:sys="using:System"\n'
    '            xmlns:pclcontrols="using:PCL.UI.Controls"\n'
    '            Margin="0,-10,0,0">\n'
)

STYLE_EXPANSION = {
    "ContentStack": {"Margin": "20,20,20,20"},
    "Card": {"Margin": "0,5"},
    "InnerImage": {"MaxHeight": "500", "HorizontalAlignment": "Center"},
    "HeadImageBorder": {
        "HorizontalAlignment": "Center",
        "BorderThickness": "4",
        "VerticalAlignment": "Top",
        "BorderBrush": "{DynamicResource ColorBrush3}",
        "CornerRadius": "7",
        "MaxHeight": "140",
    },
    "TitleBorder": {
        "Margin": "0,-20,-1,10",
        "Background": "{DynamicResource ColorBrush3}",
        "Width": "170",
        "Height": "30",
        "CornerRadius": "7",
        "BorderThickness": "0,0,0,2",
        "BorderBrush": "{DynamicResource ColorBrush2}",
    },
    "TitleBlock": {
        "HorizontalAlignment": "Center",
        "TextAlignment": "Center",
        "VerticalAlignment": "Center",
        "Foreground": "{DynamicResource ColorBrush7}",
        "Width": "180",
        "TextWrapping": "Wrap",
        "FontSize": "18",
    },
    "H1": {
        "FontSize": "24",
        "Margin": "0,10,0,10",
        "FontWeight": "Bold",
        "Foreground": "{DynamicResource ColorBrush3}",
    },
    "H2": {
        "FontSize": "22",
        "Margin": "0,10,0,5",
        "FontWeight": "Bold",
        "Foreground": "{DynamicResource ColorBrush3}",
    },
    "H3": {
        "FontSize": "18",
        "Margin": "0,5,0,5",
        "FontWeight": "Bold",
        "Foreground": "{DynamicResource ColorBrush4}",
    },
    "H5": {"FontSize": "15", "Margin": "0,3,0,5", "Foreground": "{DynamicResource ColorBrush4}"},
    "H7": {"FontSize": "14", "Margin": "0,2,0,2", "Foreground": "{DynamicResource ColorBrush4}"},
    "Quote": {
        "BorderThickness": "5,0,0,0",
        "BorderBrush": "{DynamicResource ColorBrush4}",
        "Padding": "10,5",
        "Margin": "0,5",
    },
    "imgTitle": {
        "FontSize": "14",
        "Foreground": "#FF777777",
        "HorizontalAlignment": "Center",
        "Margin": "0,0,0,15",
    },
}

DROP_STYLE_KEYS = {"TabControlStyle", "TabItemStyle"}
DROP_ATTRIBUTES = {"FocusVisualStyle", "SnapsToDevicePixels", "IsItemsHost", "CanSwap", "Visibility"}
DROPPED_ATTR_PREFIXES = ("KeyboardNavigation.", "Panel.")
INLINE_TAGS = {"Run", "Bold", "Italic", "Underline", "Span", "LineBreak", "Hyperlink"}
PCL_INLINE_CONTROLS = {"MyTextButton", "MyIconTextButton", "MyButton", "MyIconButton"}


def _split_tag(tag: str):
    if tag.startswith("{"):
        uri, _, local = tag[1:].partition("}")
        return ("pcl" if "PCL" in uri else "", local)
    return ("", tag)


def _attr_name(name: str) -> str:
    if name.startswith(X_NS):
        return "x:" + name[len(X_NS):]
    if name.startswith("{"):
        return name[1:].partition("}")[2]
    return name


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _run(text: str) -> ET.Element:
    return ET.Element("Run", {"Text": text})


class Converter:
    def __init__(self) -> None:
        self.resources: dict[str, str] = {}
        self._icon_index = 0

    # ---- 值 ----
    @staticmethod
    def fix_value(value: str) -> str:
        match = re.match(r"pack://application:,,,/(.+)$", value.strip())
        if match:
            path = re.sub(r"^images/", "Images/", match.group(1))
            return "avares://PCL.Launcher/Assets/" + path
        return value

    # ---- 属性 ----
    def convert_attributes(self, el: ET.Element) -> dict[str, str]:
        _, local = _split_tag(el.tag)
        attrs: dict[str, str] = {}
        for raw_name, raw_value in el.attrib.items():
            name = _attr_name(raw_name)
            value = self.fix_value(raw_value)

            if name in DROP_ATTRIBUTES or name.startswith(DROPPED_ATTR_PREFIXES):
                continue
            if name in ("FontFamily", "Style"):
                continue
            if name == "Theme" and local == "MyHint":
                attrs["IsWarn"] = "True" if value == "Yellow" else "False"
                continue
            if name == "ToolTip":
                name = "ToolTip.Tip"
            if name == "Logo" and re.match(r"^[Mm]\s*-?\d", value):
                self._icon_index += 1
                key = "IconPath%d" % self._icon_index
                self.resources[key] = value
                attrs["Logo"] = "{StaticResource %s}" % key
                continue
            attrs[name] = value
        return attrs

    def expand_style(self, el: ET.Element, attrs: dict[str, str]) -> dict[str, str]:
        style = el.attrib.get("Style")
        if not style:
            return attrs
        match = re.search(r"StaticResource\s+([\w.]+)", style)
        if not match or match.group(1) in DROP_STYLE_KEYS:
            return attrs
        expanded = dict(STYLE_EXPANSION.get(match.group(1), {}))
        expanded.update(attrs)
        return expanded

    # ---- 内联 ----
    def inline_children(self, el: ET.Element) -> list[ET.Element]:
        out: list[ET.Element] = []
        if el.text and el.text.strip():
            out.append(_run(el.text))
        for child in el:
            kind, local = _split_tag(child.tag)
            if local in ("FlowDocument", "Section", "TextBlock", "Paragraph"):
                out.extend(self.inline_children(child))
            elif kind == "" and local in INLINE_TAGS:
                out.append(self.convert_inline(child))
            elif kind == "pcl" and local in PCL_INLINE_CONTROLS:
                out.append(self._inline_control(self.convert_element(child)))
            else:
                out.append(self.convert_element(child))
            if child.tail and child.tail.strip():
                out.append(_run(child.tail))
        return out

    def convert_inline(self, el: ET.Element) -> ET.Element:
        _, local = _split_tag(el.tag)
        if local == "LineBreak":
            return ET.Element("LineBreak")
        node = ET.Element(local, self.convert_attributes(el))
        children = self.inline_children(el)
        if local == "Run" and len(children) == 1 and len(children[0]) == 0 \
                and "Text" in children[0].attrib:
            node.set("Text", children[0].attrib["Text"])
            return node
        for child in children:
            node.append(child)
        return node

    @staticmethod
    def _inline_control(control: ET.Element) -> ET.Element:
        holder = ET.Element("InlineUIContainer")
        holder.append(control)
        return holder

    # ---- 元素 ----
    def convert_element(self, el: ET.Element) -> ET.Element:
        kind, local = _split_tag(el.tag)
        tag = "pclcontrols:" + local if kind == "pcl" else local
        attrs = self.expand_style(el, self.convert_attributes(el))

        if kind == "pcl" and local.endswith("TextButton") and (el.text or "").strip():
            attrs.setdefault("Text", el.text.strip())

        # 内联链接：原模板的负 margin 会把行距压小，交给 .inline 样式统一补偿
        if kind == "pcl" and local in PCL_INLINE_CONTROLS:
            attrs.pop("Margin", None)
            attrs["Classes"] = "inline"

        if local == "Line":
            return ET.Element("Border", {
                "Height": attrs.get("StrokeThickness", "1"),
                "Opacity": attrs.get("Opacity", "0.7"),
                "Background": attrs.get("Stroke", "{DynamicResource ColorBrush5}"),
                "HorizontalAlignment": "Stretch",
                "Margin": attrs.get("Margin", "4"),
            })

        node = ET.Element(tag, attrs)

        if local == "Border":
            image = self._pull_brush_image(el)
            if image is not None:
                node.append(image)
                if "MaxHeight" in attrs and "Height" not in attrs:
                    node.set("Height", attrs["MaxHeight"])
                return node

        if local in ("Paragraph",):
            node.tag = "TextBlock"
            inlines = ET.SubElement(node, "TextBlock.Inlines")
            for child in self.inline_children(el):
                inlines.append(child)
            return node

        if local == "TextBlock" and (len(el) or (el.text or "").strip()):
            inlines = ET.SubElement(node, "TextBlock.Inlines")
            for child in self.inline_children(el):
                inlines.append(child)
            return node

        if local == "List":
            node.tag = "StackPanel"
            for item in el:
                if _split_tag(item.tag)[1] != "ListItem":
                    continue
                block = ET.Element("TextBlock", {
                    "TextWrapping": "Wrap",
                    "FontSize": "14",
                    "Margin": "20,0,0,2",
                    "Foreground": "{DynamicResource ColorBrush1}",
                })
                inlines = ET.SubElement(block, "TextBlock.Inlines")
                inlines.append(_run("• "))
                for child in self.inline_children(item):
                    inlines.append(child)
                node.append(block)
            return node

        if local in ("FlowDocumentScrollViewer", "FlowDocument"):
            node.tag = "StackPanel"
            for child in el:
                node.append(self.convert_element(child))
            return node

        if local == "Image":
            node.tag = "pclcontrols:MyImage"
            node.set("CornerRadius", "3")
            return node

        if local == "TabControl":
            panel = ET.SubElement(node, "TabControl.ItemsPanel")
            template = ET.SubElement(panel, "ItemsPanelTemplate")
            template.append(ET.Element("UniformGrid", {"Rows": "1"}))

        for child in el:
            child_local = _split_tag(child.tag)[1]
            if child_local in ("Style", "Resources", "StackPanel.Resources"):
                continue
            node.append(self.convert_element(child))
        return node

    def _pull_brush_image(self, border: ET.Element):
        """Border.Background 的 ImageBrush 换成 MyImage；取不到地址就原样留着"""
        brush = None
        image_el = None
        for child in list(border):
            name = _split_tag(child.tag)[1]
            if name == "Border.Background":
                brush = child
            elif name == "Image":
                image_el = child

        source = ""
        stretch = "UniformToFill"
        if brush is not None:
            for child in brush:
                if _split_tag(child.tag)[1] != "ImageBrush":
                    continue
                source = self.fix_value(
                    child.attrib.get("ImageSource") or child.attrib.get("Source") or "")
                stretch = child.attrib.get("Stretch", stretch)
        if not source and image_el is not None:
            source = self.fix_value(image_el.attrib.get("Source") or "")
        if not source:
            return None

        if brush is not None:
            border.remove(brush)
        if image_el is not None:
            border.remove(image_el)
        return ET.Element("pclcontrols:MyImage", {
            "Source": source,
            "Stretch": stretch,
            "CornerRadius": "3",
            "RenderOptions.BitmapInterpolationMode": "HighQuality",
        })


def _serialize(el: ET.Element, depth: int, out: list[str]) -> None:
    pad = "    " * depth
    attrs = "".join(' %s="%s"' % (k, _esc(v)) for k, v in el.attrib.items())
    if len(el) == 0 and not (el.text or "").strip():
        out.append("%s<%s%s />" % (pad, el.tag, attrs))
        return
    out.append("%s<%s%s>" % (pad, el.tag, attrs))
    if (el.text or "").strip():
        out.append("%s    %s" % (pad, _esc(el.text.strip())))
    for child in el:
        _serialize(child, depth + 1, out)
    out.append("%s</%s>" % (pad, el.tag))


def transform(xaml: str) -> str:
    tree = ET.fromstring(xaml)
    converter = Converter()

    body: list[str] = []
    for child in tree:
        local = _split_tag(child.tag)[1]
        if local in ("StackPanel.Resources", "Resources", "Style", "Styles"):
            continue
        body.append("")
        _serialize(converter.convert_element(child), 1, body)

    resources = ""
    if converter.resources:
        entries = "".join(
            '        <sys:String x:Key="%s">%s</sys:String>\n' % (k, _esc(v))
            for k, v in converter.resources.items())
        resources = "    <StackPanel.Resources>\n" + entries + "    </StackPanel.Resources>\n\n"

    return ("<!-- 由 src/modules/axaml_export.py 自 Custom.xaml 转出，供 PCL-CE 使用 -->\n"
            + ROOT_OPEN + "\n" + resources + STATIC_STYLES + "\n".join(body)
            + "\n</StackPanel>\n")


@on("project.genxaml.return")
def _export_axaml(*_args, result: str = "", **_kwargs):
    target = os.environ.get("MAGAZINE_AXAML_OUT")
    if not target or not isinstance(result, str) or not result.strip():
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transform(result), encoding="utf-8")


STATIC_STYLES = """    <StackPanel.Styles>
        <!-- 内联链接：InlineUIContainer 把控件底边贴在基线上，用位移补偿，不参与测量 -->
        <Style Selector="pclcontrols|MyTextButton.inline">
            <Setter Property="RenderTransform" Value="translate(0px, 3px)" />
        </Style>

        <Style Selector="TabControl">
            <Setter Property="Padding" Value="2" />
            <Setter Property="Background" Value="Transparent" />
            <Setter Property="BorderBrush" Value="#FFACACAC" />
            <Setter Property="BorderThickness" Value="0" />
            <Setter Property="Template">
                <ControlTemplate>
                    <Grid RowDefinitions="Auto,*" ClipToBounds="True">
                        <ItemsPresenter Name="PART_ItemsPresenter" Grid.Row="0"
                                        ItemsPanel="{TemplateBinding ItemsPanel}" />
                        <Border Name="PART_ContentPanel" Grid.Row="1"
                                CornerRadius="7" Background="Transparent"
                                BorderBrush="{DynamicResource ColorBrush2}" BorderThickness="0">
                            <ContentPresenter Name="PART_SelectedContentHost" Grid.Row="1"
                                              Content="{TemplateBinding SelectedContent}"
                                              ContentTemplate="{TemplateBinding SelectedContentTemplate}"
                                              HorizontalContentAlignment="Stretch" />
                        </Border>
                    </Grid>
                </ControlTemplate>
            </Setter>
        </Style>

        <Style Selector="TabControl > TabItem">
            <Setter Property="Foreground" Value="{DynamicResource ColorBrush1}" />
            <Setter Property="Background" Value="Transparent" />
            <Setter Property="BorderBrush" Value="#fff" />
            <Setter Property="Margin" Value="0,0,0,8" />
            <Setter Property="Padding" Value="0" />
            <Setter Property="HorizontalContentAlignment" Value="Center" />
            <Setter Property="VerticalContentAlignment" Value="Center" />
            <Setter Property="Template">
                <ControlTemplate>
                    <Grid Name="templateRoot" Background="Transparent">
                        <Border Name="ContentPanelI"
                                BorderBrush="{DynamicResource ColorBrush2}" BorderThickness="0,0,0,2"
                                Background="{DynamicResource ColorBrushTransparentBackground}"
                                CornerRadius="7" Height="30" Margin="2,0,2,0" />
                        <TextBlock Name="txt" Text="{TemplateBinding Header}"
                                   HorizontalAlignment="Center" VerticalAlignment="Center"
                                   TextTrimming="CharacterEllipsis"
                                   Foreground="{TemplateBinding Foreground}" />
                    </Grid>
                </ControlTemplate>
            </Setter>
        </Style>

        <Style Selector="TabItem:pointerover /template/ TextBlock#txt">
            <Setter Property="Foreground" Value="{DynamicResource ColorBrush3}" />
        </Style>
        <Style Selector="TabItem:selected">
            <Setter Property="ZIndex" Value="1" />
        </Style>
        <Style Selector="TabItem:selected /template/ TextBlock#txt">
            <Setter Property="Foreground" Value="{DynamicResource ColorBrush2}" />
        </Style>
        <Style Selector="TabItem:disabled /template/ Grid#templateRoot">
            <Setter Property="Opacity" Value="0.56" />
        </Style>

        <!-- 全局文字样式，对应原 styles.xaml 里 TargetType="TextBlock" 那条 -->
        <Style Selector="TextBlock">
            <Setter Property="HorizontalAlignment" Value="Left" />
            <Setter Property="FontSize" Value="14" />
            <Setter Property="Foreground" Value="{DynamicResource ColorBrush1}" />
        </Style>
    </StackPanel.Styles>
"""
