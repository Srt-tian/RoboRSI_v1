"""Generate the editable, source-aligned draw.io architecture (stdlib only)."""

from pathlib import Path
import xml.etree.ElementTree as E

r = Path(__file__).resolve().parents[1]
out = r / "docs/figures/architecture.drawio"
mx = E.Element("mxfile", host="app.diagrams.net")
d = E.SubElement(mx, "diagram", id="roborsi-system", name="RoboRSI execution pipeline")
model = E.SubElement(
    d,
    "mxGraphModel",
    dx="1200",
    dy="780",
    grid="1",
    page="1",
    pageWidth="1220",
    pageHeight="850",
    background="#ffffff",
)
root = E.SubElement(model, "root")
E.SubElement(root, "mxCell", id="0")
E.SubElement(root, "mxCell", id="1", parent="0")


def node(id, label, x, y, w=230, h=92, fill="#dae8fc", stroke="#6c8ebf", extra=""):
    c = E.SubElement(
        root,
        "mxCell",
        id=id,
        value=label,
        vertex="1",
        parent="1",
        style=f"rounded=1;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={stroke};strokeWidth=1.5;fontColor=#172a3a;fontFamily=Helvetica;fontSize=16;spacing=10;{extra}",
    )
    E.SubElement(
        c,
        "mxGeometry",
        x=str(x),
        y=str(y),
        width=str(w),
        height=str(h),
        attrib={"as": "geometry"},
    )


def edge(id, a, b, label="", points=(), extra=""):
    c = E.SubElement(
        root,
        "mxCell",
        id=id,
        value=label,
        edge="1",
        parent="1",
        source=a,
        target=b,
        style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=0;endArrow=block;strokeWidth=1.5;strokeColor=#526c80;fontColor=#334d60;fontSize=13;labelBackgroundColor=#ffffff;"
        + extra,
    )
    g = E.SubElement(c, "mxGeometry", relative="1", attrib={"as": "geometry"})
    if points:
        arr = E.SubElement(g, "Array", attrib={"as": "points"})
        for x, y in points:
            E.SubElement(arr, "mxPoint", x=str(x), y=str(y))


node(
    "title",
    "RoboRSI  /  coarse plans → continuous robot execution",
    50,
    20,
    1120,
    55,
    fill="none",
    stroke="none",
    extra="fontSize=26;fontStyle=1;align=left;",
)
node(
    "planning_label",
    "01  SCENE-GROUNDED PLANNING · before execution",
    50,
    86,
    1120,
    36,
    fill="none",
    stroke="none",
    extra="align=left;fontStyle=1;fontColor=#587287;fontSize=14;",
)
node(
    "scene",
    "RGB scene + task\nURDF / table reference\nPrior trial experience",
    50,
    140,
    230,
    106,
    fill="#d5e8d4",
    stroke="#82b366",
)
node(
    "gpt",
    "GPT planner\nObject order · grasp pose\nSparse task waypoints",
    340,
    140,
    230,
    106,
)
node(
    "ik",
    "URDF IK + validation\nJoint limits · pose bounds\nSampled geometry checks",
    630,
    140,
    230,
    106,
)
node(
    "smooth",
    "Deterministic smoothing\nC1 interpolation + retiming\nVelocity / acceleration bounds",
    920,
    140,
    250,
    106,
    fill="#e1d5e7",
    stroke="#9673a6",
)
edge("scene_gpt", "scene", "gpt")
edge("gpt_ik", "gpt", "ik")
edge("ik_smooth", "ik", "smooth")
node(
    "runtime_label",
    "02  CONTINUOUS EXECUTION · no new vision / VLM calls in the final trials",
    50,
    288,
    1120,
    36,
    fill="none",
    stroke="none",
    extra="align=left;fontStyle=1;fontColor=#587287;fontSize=14;",
)
node(
    "queue",
    "Target stream / queue\n512-point buffer + refill\nExplicit gripper events",
    920,
    360,
    250,
    106,
    fill="#fff2cc",
    stroke="#d6b656",
)
node(
    "worker",
    "Inference control worker\n200 Hz target updates\nOne writer · every 5 ms",
    630,
    360,
    230,
    106,
    fill="#ffe6cc",
    stroke="#d79b00",
)
node(
    "robot",
    "Piper robot\nLeft arm executes\nRight arm holds",
    340,
    360,
    230,
    106,
    fill="#d5e8d4",
    stroke="#82b366",
)
node(
    "monitor",
    "Feedback supervisor\n~50 Hz state checks\nTracking · height · grip",
    50,
    360,
    230,
    106,
    fill="#e1d5e7",
    stroke="#9673a6",
)
edge("smooth_queue", "smooth", "queue")
edge("queue_worker", "queue", "worker")
edge("worker_robot", "worker", "robot")
edge("robot_monitor", "robot", "monitor")
node(
    "hold",
    "On fault: measured hold\nCancel writer · clear queue\nRetain torque and grip",
    50,
    560,
    230,
    106,
    fill="#f8cecc",
    stroke="#b85450",
)
node(
    "logs",
    "Recorded evidence\nCommands + measured state\nTask outcome separately",
    340,
    560,
    230,
    106,
    fill="#d5e8d4",
    stroke="#82b366",
)
node(
    "web",
    "Local experiment viewer\nTiming · errors · before / after\nSummarize after execution",
    630,
    560,
    230,
    106,
)
node(
    "rsi",
    "Next-trial refinement\nHuman-reviewed corrections\nNo learned online RSI yet",
    920,
    560,
    250,
    106,
    fill="#f5f5f5",
    stroke="#666666",
    extra="dashed=1;",
)
edge("monitor_hold", "monitor", "hold", "fault")
edge("robot_logs", "robot", "logs", "record")
edge("logs_web", "logs", "web")
edge("web_rsi", "web", "rsi", "review", extra="dashed=1;")
node(
    "footnote",
    "Validated: 3 objects / 85.42 s / measured 200 Hz.  Small VLM disabled.\nIK is not full scene collision checking; a nonzero gripper width is not proof of task success.",
    50,
    718,
    1120,
    68,
    fill="#f5f5f5",
    stroke="#d0d9e2",
    extra="fontSize=14;align=left;",
)
E.indent(mx)
out.write_text(E.tostring(mx, encoding="unicode"))
print(out)
