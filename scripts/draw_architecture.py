"""Regenerate the architecture and execution flow with editable native draw.io cells."""

import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs/figures"
PALETTE = {
    "blue": ("#EAF2FC", "#6186B1"),
    "purple": ("#F0EAF8", "#9B7AB8"),
    "teal": ("#E5F4EF", "#5D9C87"),
    "amber": ("#FFF3D9", "#BA994D"),
    "red": ("#FBE9E7", "#BD726C"),
    "gray": ("#F3F5F8", "#A0ADBB"),
}


class Diagram:
    def __init__(self, name, width, height):
        self.name = name
        self.xml = ET.Element("mxfile", host="app.diagrams.net")
        page = ET.SubElement(self.xml, "diagram", id=f"roborsi-{name}", name=name)
        model = ET.SubElement(
            page,
            "mxGraphModel",
            page="1",
            pageWidth=str(width),
            pageHeight=str(height),
            background="#FFFFFF",
        )
        self.root = ET.SubElement(model, "root")
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")

    def box(self, key, label, x, y, w=290, h=130, color="blue", extra=""):
        fill, stroke = PALETTE[color]
        cell = ET.SubElement(
            self.root,
            "mxCell",
            id=key,
            value=label,
            parent="1",
            vertex="1",
            style="rounded=1;whiteSpace=wrap;html=1;"
            f"fillColor={fill};strokeColor={stroke};strokeWidth=1.5;"
            "fontFamily=Noto Sans CJK SC;fontSize=17;fontColor=#20374C;"
            "spacing=12;arcSize=12;" + extra,
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            x=str(x),
            y=str(y),
            width=str(w),
            height=str(h),
            attrib={"as": "geometry"},
        )

    def text(self, key, label, x, y, w, h=55, size=18):
        self.box(
            key,
            label,
            x,
            y,
            w,
            h,
            extra=f"fillColor=none;strokeColor=none;align=left;fontSize={size};",
        )

    def edge(
        self,
        key,
        source,
        target,
        label="",
        ports="",
        points=(),
        dashed=False,
        red=False,
    ):
        cell = ET.SubElement(
            self.root,
            "mxCell",
            id=key,
            source=source,
            target=target,
            value=label,
            parent="1",
            edge="1",
            style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
            "jettySize=auto;html=1;endArrow=block;strokeWidth=1.6;"
            "fontFamily=Noto Sans CJK SC;fontSize=14;labelBackgroundColor=#FFFFFF;"
            f"strokeColor={'#BD726C' if red else '#638097'};fontColor=#425C72;"
            + ports
            + ("dashed=1;" if dashed else ""),
        )
        geo = ET.SubElement(cell, "mxGeometry", relative="1", attrib={"as": "geometry"})
        if points:
            arr = ET.SubElement(geo, "Array", attrib={"as": "points"})
            for x, y in points:
                ET.SubElement(arr, "mxPoint", x=str(x), y=str(y))

    def save(self):
        OUT.mkdir(parents=True, exist_ok=True)
        ET.indent(self.xml)
        path = OUT / f"{self.name}.drawio"
        ET.ElementTree(self.xml).write(path, encoding="utf-8", xml_declaration=True)
        print(path)


def architecture():
    d = Diagram("architecture", 1480, 870)
    d.text("title", "<b>RoboRSI v1 · 从粗计划到连续操作</b>", 40, 20, 1370, 65, 30)
    d.text(
        "subtitle",
        "本轮：固定计划执行　｜　跨轮：人工审核经验修订　｜　任务结果独立确认",
        40,
        90,
        1370,
    )
    d.box(
        "scene",
        "<b>01 · 场景与任务</b><br><br>启动前图像 / 物体与篮筐<br>当前关节状态 / 桌面参考<br>已审核的历史经验",
        40,
        185,
        h=160,
        color="gray",
    )
    d.box(
        "planner",
        "<b>02 · 粗粒度规划</b><br><br>交互式 GPT 决定顺序与姿态<br>调用运动学工具辅助选点<br>人工审核粗关节路径",
        400,
        185,
        h=160,
        color="blue",
    )
    d.box(
        "compiler",
        "<b>03 · 确定性轨迹编译</b><br><br>C1 插值 / 速度与加速度限值<br>独立夹爪事件 / 可选 URDF 检查<br>输出固定 200 Hz 目标流",
        760,
        185,
        h=160,
        color="purple",
    )
    d.box(
        "runtime",
        "<b>04 · 连续执行与监督</b><br><br>512 点队列 / 唯一写线程<br>200 Hz 下发 + 约 50 Hz 监督<br>异常或结束后实测保持",
        1120,
        185,
        h=160,
        color="teal",
    )
    d.box(
        "review",
        "<b>RSI · 人工审核修订</b><br><br>诊断定位 / 抓取 / 执行问题<br>修订抓取深度、方向与关键点<br><b>仅用于下一轮重新规划</b>",
        400,
        545,
        h=150,
        color="purple",
    )
    d.box(
        "evidence",
        "<b>执行后 · 记录与结果确认</b><br><br>实测反馈 → 本机 Web<br>命令归档 / 结果图像 / 现场确认<br>程序完成 ≠ 物体已入筐",
        760,
        545,
        h=150,
        color="amber",
    )
    d.box(
        "robot",
        "<b>Piper · 设备与关节反馈</b><br><br>左臂执行 / 右臂保持<br>关节位置 / TCP / 夹爪宽度<br>无执行中视觉模型调用",
        1120,
        545,
        h=150,
        color="teal",
    )
    d.text(
        "roles",
        "<b>职责边界</b><br>GPT：决定去哪里、怎么夹<br>编译器：生成细粒度目标<br>控制线程：按固定周期下发",
        40,
        545,
        310,
        150,
        17,
    )
    lr = "exitX=1;exitY=.5;entryX=0;entryY=.5;"
    d.edge("scene-plan", "scene", "planner", "任务上下文", lr)
    d.edge("plan-compile", "planner", "compiler", "粗计划 JSON", lr)
    d.edge("compile-run", "compiler", "runtime", "目标流 JSON", lr)
    d.edge(
        "commands",
        "runtime",
        "robot",
        "200 Hz 目标",
        "exitX=.3;exitY=1;entryX=.3;entryY=0;",
    )
    d.edge(
        "feedback",
        "robot",
        "runtime",
        "反馈与监督",
        "exitX=.75;exitY=0;entryX=.75;entryY=1;",
    )
    d.edge(
        "robot-evidence",
        "robot",
        "evidence",
        "执行证据",
        "exitX=0;exitY=.5;entryX=1;entryY=.5;",
    )
    d.edge(
        "evidence-review",
        "evidence",
        "review",
        "复盘",
        "exitX=0;exitY=.5;entryX=1;entryY=.5;",
        dashed=True,
    )
    d.edge(
        "next-trial",
        "review",
        "planner",
        "下一轮 · 非在线自动学习",
        "exitX=.5;exitY=0;entryX=.5;entryY=1;",
        dashed=True,
    )
    d.text(
        "footer",
        "规划通过交互会话完成；仓库不包含独立 GPT API 服务。编译器读取已审核关节路径，不自动生成抓取策略。<br>实线：本轮数据与执行　　虚线：跨轮人机监督的 RSI 修订",
        40,
        755,
        1370,
        80,
        16,
    )
    d.save()


def execution_flow():
    d = Diagram("execution_flow", 1280, 1720)
    d.text("title", "<b>RoboRSI v1 · 一轮任务如何执行</b>", 40, 20, 1190, 65, 30)
    d.text(
        "subtitle",
        "默认离线；真机显式开启。执行保护不会调用 GPT 重规划，也不会自动续跑。",
        40,
        95,
        1190,
    )
    x, w = 430, 350
    d.box(
        "program",
        "<b>审核粗计划</b><br>关节关键点 + 夹爪事件 + 初始状态",
        x,
        180,
        w,
        85,
    )
    d.box(
        "compile",
        "<b>离线编译 roborsi-compile</b><br>插值 / 重定时 / 检查 / 固定目标流",
        x,
        325,
        w,
        95,
        color="purple",
    )
    diamond = "rhombus;rounded=0;"
    d.box(
        "execute", "显式 --execute？", 490, 480, 230, 110, color="amber", extra=diamond
    )
    d.box(
        "offline",
        "<b>离线完成</b><br>编译 / dry 检查<br>可查看历史反馈，零硬件写入",
        40,
        485,
        290,
        110,
        color="gray",
    )
    d.box(
        "preflight",
        "执行前检查通过？",
        490,
        655,
        230,
        110,
        color="amber",
        extra=diamond,
    )
    d.box(
        "reject",
        "<b>拒绝启动</b><br>修订场景 / 配置 / 计划<br>不启动目标流",
        920,
        655,
        290,
        110,
        color="red",
    )
    d.box(
        "stream",
        "<b>连续执行固定目标流</b><br>200 Hz 写线程 + 约 50 Hz 监督<br>按事件检查夹爪；低水位补队列",
        x,
        825,
        w,
        115,
        color="teal",
    )
    d.box(
        "fault",
        "保护触发 / 用户停止？",
        475,
        1000,
        260,
        110,
        color="amber",
        extra=diamond,
    )
    d.box(
        "done", "目标流完成且收敛？", 475, 1170, 260, 110, color="amber", extra=diamond
    )
    d.box(
        "hold",
        "<b>停止并尝试实测保持</b><br>停写线程 → 清队列 → 新鲜状态<br>保留扭矩与夹爪，不自动续跑",
        920,
        1170,
        290,
        130,
        color="red",
    )
    d.box(
        "save",
        "<b>执行后保存与可视化</b><br>命令 / 反馈 / 完成或异常状态<br>本机 Web 播放实测反馈",
        x,
        1380,
        w,
        110,
        color="amber",
    )
    d.box(
        "outcome",
        "<b>独立确认任务结果</b><br>结果图像 + 现场确认 → 人工复盘<br>审核后的经验用于下一轮",
        x,
        1550,
        w,
        100,
        color="purple",
    )
    down = "exitX=.5;exitY=1;entryX=.5;entryY=0;"
    d.edge("program-compile", "program", "compile", ports=down)
    d.edge("compile-execute", "compile", "execute", ports=down)
    d.edge("dry", "execute", "offline", "否", "exitX=0;exitY=.5;entryX=1;entryY=.5;")
    d.edge("live", "execute", "preflight", "是", down)
    d.edge(
        "reject-run",
        "preflight",
        "reject",
        "否",
        "exitX=1;exitY=.5;entryX=0;entryY=.5;",
        red=True,
    )
    d.edge("start-run", "preflight", "stream", "是", down)
    d.edge("watch", "stream", "fault", ports=down)
    d.edge(
        "stop",
        "fault",
        "hold",
        "是 · 异常/停止",
        "exitX=1;exitY=.5;entryX=.5;entryY=0;",
        points=((1065, 1055),),
        red=True,
    )
    d.edge("healthy", "fault", "done", "否", down)
    d.edge(
        "continue",
        "done",
        "stream",
        "否 · 继续监督",
        "exitX=0;exitY=.5;entryX=0;entryY=.5;",
        points=((370, 1225), (370, 882)),
    )
    d.edge(
        "complete",
        "done",
        "hold",
        "是 · 正常完成",
        "exitX=1;exitY=.5;entryX=0;entryY=.5;",
    )
    d.edge(
        "hold-save",
        "hold",
        "save",
        "保留完成 / 异常原因",
        "exitX=.5;exitY=1;entryX=1;entryY=.5;",
        points=((1065, 1435),),
    )
    d.edge("save-outcome", "save", "outcome", ports=down)
    d.save()


if __name__ == "__main__":
    architecture()
    execution_flow()
