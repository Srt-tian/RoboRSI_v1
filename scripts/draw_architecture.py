"""Generate editable draw.io diagrams for architecture, RSI, and execution."""

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

    def box(self, key, label, x, y, w=290, h=130, color="blue", extra="", parent="1"):
        fill, stroke = PALETTE[color]
        cell = ET.SubElement(
            self.root,
            "mxCell",
            id=key,
            value=label,
            parent=parent,
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
    d = Diagram("architecture", 1440, 1290)
    d.text("title", "<b>RoboRSI v1 · RSI 驱动的四层框架</b>", 60, 20, 1300, 65, 30)
    lane = "container=1;pointerEvents=0;verticalAlign=top;align=left;spacingTop=16;spacingLeft=22;fontStyle=1;fontSize=19;"
    for key, title, y, height, color in [
        ("rsi_layer", "L1  RSI 跨轮改进层 · 执行之后 / 人工审核", 150, 230, "purple"),
        ("planning_layer", "L2  任务规划层 · 新一轮开始之前", 450, 190, "blue"),
        ("compilation_layer", "L3  轨迹编译层 · 确定性计算", 710, 190, "amber"),
        ("execution_layer", "L4  执行与反馈层 · 本轮固定计划", 970, 190, "teal"),
    ]:
        d.box(key, title, 60, y, 1320, height, color=color, extra=lane)
    child = "fillColor=#FFFFFF;"
    d.box(
        "evidence",
        "<b>收集实验证据</b><br>命令 / 实测反馈 / 故障<br>结果图像 + 现场任务确认",
        30,
        75,
        360,
        110,
        color="purple",
        extra=child,
        parent="rsi_layer",
    )
    d.box(
        "review",
        "<b>诊断与修订建议</b><br>定位 / 姿态 / 抓取 / 执行<br>区分观测事实与原因假设",
        470,
        75,
        360,
        110,
        color="purple",
        extra=child,
        parent="rsi_layer",
    )
    d.box(
        "experience",
        "<b>人工审核经验</b><br>适用条件 / 修改项 / 验证结果<br>供下一轮规划选择使用",
        910,
        75,
        360,
        110,
        color="purple",
        extra=child,
        parent="rsi_layer",
    )
    d.box(
        "scene",
        "<b>本轮上下文</b><br>新鲜场景 + 初始状态 + 任务<br>人工选用已审核经验",
        30,
        65,
        520,
        100,
        extra=child,
        parent="planning_layer",
    )
    d.box(
        "planner",
        "<b>GPT 粗规划 + IK 工具</b><br>物体顺序 / 抓取姿态 / 关节关键点<br>交互会话产出审核后的粗计划",
        750,
        65,
        540,
        100,
        extra=child,
        parent="planning_layer",
    )
    d.box(
        "constraints",
        "<b>约束与事件</b><br>URDF / 几何 / 速度与加速度<br>夹爪开合与驻留独立定义",
        30,
        65,
        520,
        100,
        color="amber",
        extra=child,
        parent="compilation_layer",
    )
    d.box(
        "compiler",
        "<b>确定性轨迹编译器</b><br>C1 插值 + 重定时 + 检查<br>生成固定 200 Hz 目标流",
        750,
        65,
        540,
        100,
        color="amber",
        extra=child,
        parent="compilation_layer",
    )
    d.box(
        "monitor",
        "<b>实测反馈与保护</b><br>约 50 Hz 监督 / 异常保持<br>执行后日志与本机 Web",
        30,
        65,
        520,
        100,
        color="teal",
        extra=child,
        parent="execution_layer",
    )
    d.box(
        "runtime",
        "<b>高频执行器 + Piper</b><br>512 点队列 / 唯一 200 Hz 写线程<br>左臂执行，右臂保持",
        750,
        65,
        540,
        100,
        color="teal",
        extra=child,
        parent="execution_layer",
    )
    lr = "exitX=1;exitY=.5;entryX=0;entryY=.5;"
    d.edge("evidence-review", "evidence", "review", "复盘", lr, dashed=True)
    d.edge("review-experience", "review", "experience", "审核", lr, dashed=True)
    d.edge(
        "experience-plan",
        "experience",
        "planning_layer",
        "下一轮采用 / 重新验证",
        "exitX=.5;exitY=1;entryX=.82;entryY=0;",
        dashed=True,
    )
    d.edge("scene-planner", "scene", "planner", "规划上下文", lr)
    d.edge("constraints-compiler", "constraints", "compiler", "约束输入", lr)
    down = "exitX=.82;exitY=1;entryX=.82;entryY=0;"
    d.edge("plan-compile", "planning_layer", "compilation_layer", "粗计划 JSON", down)
    d.edge(
        "compile-execute",
        "compilation_layer",
        "execution_layer",
        "固定目标流 JSON",
        down,
    )
    d.edge(
        "runtime-monitor",
        "runtime",
        "monitor",
        "命令与反馈",
        "exitX=0;exitY=.5;entryX=1;entryY=.5;",
    )
    d.edge(
        "trial-evidence",
        "execution_layer",
        "evidence",
        "",
        "exitX=0;exitY=.5;entryX=0;entryY=.5;",
        points=((20, 1065), (20, 280)),
    )
    d.text(
        "footer",
        "外侧回路：本轮证据进入 RSI 复盘；虚线：人工监督的跨轮修订。<br>当前无自动训练或经验检索服务；本轮执行不调用视觉模型。经验需结合新场景重新审核。",
        60,
        1200,
        1320,
        75,
        16,
    )
    d.save()


def rsi_cycle():
    d = Diagram("rsi_cycle", 1360, 830)
    d.text("title", "<b>RSI 改进闭环 · 改什么、怎么验证</b>", 40, 20, 1270, 65, 30)
    d.text(
        "subtitle",
        "当前为人机监督的跨轮迭代；经验是带证据与适用条件的修订，不是自动更新的模型权重。",
        40,
        90,
        1270,
    )
    d.box(
        "trial",
        "<b>本轮执行证据 Dₖ</b><br>命令 / 反馈 / 任务结果<br>记录失败与人工干预",
        40,
        195,
        280,
        130,
        color="teal",
    )
    d.box(
        "diagnose",
        "<b>问题诊断</b><br>观测事实 + 原因假设<br>选择需要修订的层",
        370,
        195,
        280,
        130,
        color="purple",
    )
    d.box(
        "candidate",
        "<b>候选修订 Δₖ</b><br>修改值 / 适用场景 / 风险<br>列出下一轮验证标准",
        700,
        195,
        280,
        130,
        color="purple",
    )
    d.box(
        "approve",
        "<b>人工审核</b><br>采用 / 驳回 / 继续观察<br>未审核修订不进入新计划",
        1030,
        195,
        280,
        130,
        color="amber",
    )
    d.box(
        "compare",
        "<b>比较与保留证据</b><br>成功、失败都归档<br>多项同时修改不作单因归因",
        40,
        475,
        350,
        140,
        color="teal",
    )
    d.box(
        "next",
        "<b>下一轮重新验证</b><br>新鲜场景 + 状态 → 新计划<br>重新编译 / 检查 / 执行",
        500,
        475,
        350,
        140,
        color="blue",
    )
    d.box(
        "experience",
        "<b>审核后的经验 Eₖ₊₁</b><br>适用条件与证据链接<br>人工选择后注入规划上下文",
        960,
        475,
        350,
        140,
        color="purple",
    )
    lr = "exitX=1;exitY=.5;entryX=0;entryY=.5;"
    rl = "exitX=0;exitY=.5;entryX=1;entryY=.5;"
    d.edge("evidence-diagnosis", "trial", "diagnose", ports=lr)
    d.edge("diagnosis-change", "diagnose", "candidate", ports=lr)
    d.edge("change-review", "candidate", "approve", ports=lr)
    d.edge(
        "approved",
        "approve",
        "experience",
        "采用",
        "exitX=.5;exitY=1;entryX=.5;entryY=0;",
        dashed=True,
    )
    d.edge("apply", "experience", "next", "新一轮采用", rl, dashed=True)
    d.edge("evaluate", "next", "compare", ports=rl)
    d.edge(
        "new-evidence",
        "compare",
        "trial",
        "新证据 Dₖ₊₁",
        "exitX=.35;exitY=0;entryX=.5;entryY=1;",
    )
    d.text(
        "case",
        "<b>记录实例：</b>首轮青椒空夹 → 调整抓取深度与方向 → 下一轮三物体入筐。<br>这说明发生了可追溯修订；单轮成功不能证明单一改动的收益，也不能推导长期成功率。",
        40,
        680,
        1270,
        95,
        17,
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
    rsi_cycle()
    execution_flow()
