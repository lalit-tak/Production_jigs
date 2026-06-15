"""
Generate diagnostic flowcharts as SVG using pure Python (no external tools).
Each flowchart is a self-contained SVG string, embedded directly into the HTML.
"""

# ─── Palette ────────────────────────────────────────────────────────────────
C_HEADER   = "#1e3a5f"   # dark navy – start/end rounded rect
C_PROCESS  = "#1d4ed8"   # blue – process box
C_DECISION = "#0369a1"   # mid-blue – diamond
C_ACTION   = "#065f46"   # dark green – action / fix box
C_WARN     = "#92400e"   # amber – warning / escalate
C_EDGE     = "#374151"   # edge colour
C_WHITE    = "#ffffff"
C_LIGHT    = "#eff6ff"
C_LTGREEN  = "#d1fae5"
C_LTAMBER  = "#fef3c7"
C_LTERED   = "#fee2e2"

FONT = "Inter, Arial, sans-serif"
NODE_W  = 200
NODE_H  = 38
DIA_W   = 220
DIA_H   = 52
TERM_W  = 180
TERM_H  = 34


class SVGFlowchart:
    def __init__(self, width=640, title=""):
        self.width   = width
        self.title   = title
        self.items   = []   # list of (type, id, label, x, y, extra)
        self.edges   = []   # list of (from_id, to_id, label, style)
        self._id_map = {}   # id -> (cx, cy, w, h, shape)
        self.height  = 60

    # ── nodes ──────────────────────────────────────────────────────────────
    def term(self, nid, label, x, y, color=C_HEADER):
        """Terminal (rounded rect) – start / end."""
        self.items.append(("term", nid, label, x, y, color))
        self._id_map[nid] = (x, y, TERM_W, TERM_H, "term")
        self.height = max(self.height, y + TERM_H + 30)

    def proc(self, nid, label, x, y, color=C_PROCESS, bg=C_LIGHT):
        """Process rectangle."""
        self.items.append(("proc", nid, label, x, y, (color, bg)))
        self._id_map[nid] = (x, y, NODE_W, NODE_H, "proc")
        self.height = max(self.height, y + NODE_H + 30)

    def decision(self, nid, label, x, y):
        """Decision diamond."""
        self.items.append(("deci", nid, label, x, y, None))
        self._id_map[nid] = (x, y, DIA_W, DIA_H, "deci")
        self.height = max(self.height, y + DIA_H + 30)

    def action(self, nid, label, x, y, color=C_ACTION, bg=C_LTGREEN):
        """Action / fix box."""
        self.items.append(("act", nid, label, x, y, (color, bg)))
        self._id_map[nid] = (x, y, NODE_W, NODE_H, "act")
        self.height = max(self.height, y + NODE_H + 30)

    def warn(self, nid, label, x, y):
        """Warning / escalate box."""
        self.items.append(("warn", nid, label, x, y, None))
        self._id_map[nid] = (x, y, NODE_W, NODE_H, "warn")
        self.height = max(self.height, y + NODE_H + 30)

    # ── edges ──────────────────────────────────────────────────────────────
    def edge(self, fid, tid, label="", style="normal"):
        self.edges.append((fid, tid, label, style))

    # ── render helpers ─────────────────────────────────────────────────────
    def _wrap(self, text, maxw=26):
        """Wrap long labels."""
        words = text.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 > maxw and cur:
                lines.append(cur.strip())
                cur = w + " "
            else:
                cur += w + " "
        if cur.strip():
            lines.append(cur.strip())
        return lines

    def _text_svg(self, x, y, lines, color="#fff", size=10, bold=False):
        dy = 14 if len(lines) == 1 else 12
        start_y = y - (len(lines) - 1) * dy / 2
        weight = "bold" if bold else "normal"
        out = ""
        for i, ln in enumerate(lines):
            out += (f'<text x="{x}" y="{start_y + i*dy}" '
                    f'text-anchor="middle" fill="{color}" '
                    f'font-family="{FONT}" font-size="{size}" '
                    f'font-weight="{weight}">{ln}</text>')
        return out

    def _anchor(self, nid, side):
        """Return (x,y) anchor point on side: top/bottom/left/right."""
        cx, cy, w, h, shape = self._id_map[nid]
        if side == "top":    return cx, cy - h/2
        if side == "bottom": return cx, cy + h/2
        if side == "left":   return cx - w/2, cy
        if side == "right":  return cx + w/2, cy

    def _arrow(self, x1, y1, x2, y2, label="", color=C_EDGE):
        path = f"M{x1},{y1} L{x2},{y2}"
        out = (f'<defs><marker id="arr" markerWidth="8" markerHeight="8" '
               f'refX="6" refY="3" orient="auto">'
               f'<path d="M0,0 L0,6 L8,3 z" fill="{color}"/></marker></defs>'
               f'<path d="{path}" stroke="{color}" stroke-width="1.5" '
               f'fill="none" marker-end="url(#arr)"/>')
        if label:
            mx, my = (x1+x2)/2, (y1+y2)/2
            out += (f'<rect x="{mx-18}" y="{my-8}" width="36" height="14" '
                    f'fill="white" opacity="0.85"/>'
                    f'<text x="{mx}" y="{my+3}" text-anchor="middle" '
                    f'fill="{color}" font-family="{FONT}" font-size="9" '
                    f'font-weight="bold">{label}</text>')
        return out

    def _bent_arrow(self, x1, y1, x2, y2, label="", color=C_EDGE, bend="right"):
        """L-shaped arrow."""
        if bend == "right":
            mid_x, mid_y = x2, y1
        else:
            mid_x, mid_y = x1, y2
        path = f"M{x1},{y1} L{mid_x},{mid_y} L{x2},{y2}"
        out = (f'<path d="{path}" stroke="{color}" stroke-width="1.5" '
               f'fill="none" marker-end="url(#arr)"/>')
        if label:
            mx, my = (mid_x+x2)/2, (mid_y+y2)/2
            out += (f'<rect x="{mx-18}" y="{my-8}" width="36" height="14" '
                    f'fill="white" opacity="0.85"/>'
                    f'<text x="{mx}" y="{my+3}" text-anchor="middle" '
                    f'fill="{color}" font-family="{FONT}" font-size="9" '
                    f'font-weight="bold">{label}</text>')
        return out

    def render(self):
        h = self.height + 60
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" '
               f'width="{self.width}" height="{h}" '
               f'style="font-family:{FONT};background:#f8fafc;border-radius:8px;">']

        # Background
        svg.append(f'<rect width="{self.width}" height="{h}" rx="8" fill="#f8fafc"/>')

        # Title
        if self.title:
            svg.append(f'<text x="{self.width//2}" y="26" text-anchor="middle" '
                       f'fill="{C_HEADER}" font-family="{FONT}" font-size="13" '
                       f'font-weight="bold">{self.title}</text>')

        # Arrow defs (global)
        svg.append(f'<defs><marker id="arr" markerWidth="8" markerHeight="8" '
                   f'refX="6" refY="3" orient="auto">'
                   f'<path d="M0,0 L0,6 L8,3 z" fill="{C_EDGE}"/></marker></defs>')

        # Nodes
        for item in self.items:
            kind, nid, label, x, y, extra = item
            lines = self._wrap(label)

            if kind == "term":
                color = extra
                svg.append(f'<rect x="{x-TERM_W//2}" y="{y-TERM_H//2}" '
                           f'width="{TERM_W}" height="{TERM_H}" rx="17" '
                           f'fill="{color}" stroke="{color}"/>')
                svg.append(self._text_svg(x, y, lines, "#fff", 10, True))

            elif kind in ("proc", "act"):
                border, bg = extra
                svg.append(f'<rect x="{x-NODE_W//2}" y="{y-NODE_H//2}" '
                           f'width="{NODE_W}" height="{NODE_H}" rx="4" '
                           f'fill="{bg}" stroke="{border}" stroke-width="1.5"/>')
                svg.append(self._text_svg(x, y, lines, border, 9, True))

            elif kind == "deci":
                hw, hh = DIA_W//2, DIA_H//2
                pts = f"{x},{y-hh} {x+hw},{y} {x},{y+hh} {x-hw},{y}"
                svg.append(f'<polygon points="{pts}" '
                           f'fill="{C_LTAMBER}" stroke="{C_DECISION}" stroke-width="1.5"/>')
                svg.append(self._text_svg(x, y, lines, C_DECISION, 9, True))

            elif kind == "warn":
                svg.append(f'<rect x="{x-NODE_W//2}" y="{y-NODE_H//2}" '
                           f'width="{NODE_W}" height="{NODE_H}" rx="4" '
                           f'fill="{C_LTAMBER}" stroke="{C_WARN}" stroke-width="1.5"/>')
                svg.append(self._text_svg(x, y, lines, C_WARN, 9, True))

        # Edges
        for fid, tid, label, style in self.edges:
            cx1, cy1, w1, h1, s1 = self._id_map[fid]
            cx2, cy2, w2, h2, s2 = self._id_map[tid]

            # simple vertical
            if abs(cx1 - cx2) < 5:
                x1, y1 = cx1, cy1 + h1/2
                x2, y2 = cx2, cy2 - h2/2
                svg.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="{C_EDGE}" '
                           f'stroke-width="1.5" fill="none" marker-end="url(#arr)"/>')
                if label:
                    mx, my = (x1+x2)/2, (y1+y2)/2
                    svg.append(f'<rect x="{mx-20}" y="{my-8}" width="40" height="14" '
                               f'fill="white" opacity="0.9" rx="3"/>'
                               f'<text x="{mx}" y="{my+3}" text-anchor="middle" '
                               f'fill="{C_EDGE}" font-family="{FONT}" font-size="9" '
                               f'font-weight="bold">{label}</text>')
            else:
                # horizontal then vertical
                if cx2 > cx1:
                    x1, y1 = cx1 + w1/2, cy1
                else:
                    x1, y1 = cx1 - w1/2, cy1
                if cy2 > cy1:
                    x2, y2 = cx2, cy2 - h2/2
                else:
                    x2, y2 = cx2, cy2 + h2/2
                mid_x = x2
                svg.append(f'<path d="M{x1},{y1} L{mid_x},{y1} L{mid_x},{y2}" '
                           f'stroke="{C_EDGE}" stroke-width="1.5" fill="none" '
                           f'marker-end="url(#arr)"/>')
                if label:
                    mx, my = (x1 + mid_x)/2, y1
                    svg.append(f'<rect x="{mx-20}" y="{my-10}" width="40" height="14" '
                               f'fill="white" opacity="0.9" rx="3"/>'
                               f'<text x="{mx}" y="{my+1}" text-anchor="middle" '
                               f'fill="{C_EDGE}" font-family="{FONT}" font-size="9" '
                               f'font-weight="bold">{label}</text>')

        svg.append('</svg>')
        return '\n'.join(svg)


# ════════════════════════════════════════════════════════════════════════════
# BUILD ALL 6 FLOWCHARTS
# ════════════════════════════════════════════════════════════════════════════

def fc_app_not_launching():
    f = SVGFlowchart(660, "6.1  Application Not Launching")
    cx = 330
    f.term("start", "Application fails to launch", cx, 55)
    f.decision("err", "Python error shown?", cx, 120)
    f.proc("mnfe", "ModuleNotFoundError", 130, 190, C_PROCESS)
    f.proc("pw32", "pywin32 / COM error", 330, 190, C_PROCESS)
    f.proc("tkr",  "Tkinter missing", 520, 190, C_PROCESS)
    f.action("fix1","pip install -r requirements.txt", 130, 260, C_ACTION, C_LTGREEN)
    f.action("fix2","pip install pywin32\n+ run postinstall as Admin", 330, 260, C_ACTION, C_LTGREEN)
    f.action("fix3","Reinstall Python with tk", 520, 260, C_ACTION, C_LTGREEN)
    f.decision("noerr","No error — EXE or PY?", cx, 340)
    f.proc("exe","EXE: check antivirus\nRun as Admin", 180, 410, C_WARN)
    f.proc("py", "PY: verify Python ≥3.12", 480, 410, C_WARN)
    f.decision("ok","Launched OK?", cx, 490)
    f.action("chklog","Check program_log.txt\nfor CRITICAL errors", 180, 560, C_WARN)
    f.term("done","Proceed to hardware checks", cx, 560, C_ACTION)

    f.edge("start","err")
    f.edge("err","mnfe","Yes")
    f.edge("err","pw32","Yes")
    f.edge("err","tkr","Yes")
    f.edge("mnfe","fix1")
    f.edge("pw32","fix2")
    f.edge("tkr","fix3")
    f.edge("err","noerr","No")
    f.edge("noerr","exe","EXE")
    f.edge("noerr","py","PY")
    f.edge("exe","ok")
    f.edge("py","ok")
    f.edge("fix1","ok")
    f.edge("fix2","ok")
    f.edge("fix3","ok")
    f.edge("ok","chklog","No")
    f.edge("ok","done","Yes")
    return f.render()


def fc_hw_not_detected():
    f = SVGFlowchart(660, "6.2  Hardware Not Detected")
    cx = 330
    f.term("start","Hardware not detected", cx, 55)
    f.decision("which","Which hardware?", cx, 120)
    f.proc("bdaq","BDaq USB-4716 / USB-4704", 130, 190)
    f.proc("fpa","FPA Gang Programmer", 330, 190)
    f.proc("com","COM Port / USB-Serial", 530, 190)

    f.decision("bdaq_vis","Device Manager:\nAdvantec device visible?", 130, 270)
    f.action("bdaq_drv","Install Advantech DAQ driver\nReconnect USB", 60, 360, C_ACTION, C_LTGREEN)
    f.action("bdaq_chk","Verify DeviceName in BDaqApi\nCheck USB power / hub", 200, 360, C_ACTION, C_LTGREEN)

    f.decision("fpa_cnt","Connected adapters = 0?", 330, 270)
    f.action("fpa_usb","Check USB cable to FPA\nVerify FPAs-setup.ini path\nReinstall GangPro driver", 260, 360, C_ACTION, C_LTGREEN)
    f.action("fpa_cfg","Check serial# in log\nVerify GangConfig .cfg file", 400, 360, C_ACTION, C_LTGREEN)

    f.decision("com_vis","Device Manager:\nCOMx visible?", 530, 270)
    f.action("com_drv","Reinstall USB-serial driver\nTry different USB port", 460, 360, C_ACTION, C_LTGREEN)
    f.action("com_cfg","Port # matches config?\nNot held by another app?", 600, 360, C_ACTION, C_LTGREEN)

    f.term("end","Hardware detected — proceed", cx, 450, C_ACTION)

    f.edge("start","which")
    f.edge("which","bdaq","BDaq")
    f.edge("which","fpa","FPA")
    f.edge("which","com","COM")
    f.edge("bdaq","bdaq_vis")
    f.edge("bdaq_vis","bdaq_drv","No")
    f.edge("bdaq_vis","bdaq_chk","Yes")
    f.edge("fpa","fpa_cnt")
    f.edge("fpa_cnt","fpa_usb","Yes")
    f.edge("fpa_cnt","fpa_cfg","No")
    f.edge("com","com_vis")
    f.edge("com_vis","com_drv","No")
    f.edge("com_vis","com_cfg","Yes")
    f.edge("bdaq_drv","end")
    f.edge("bdaq_chk","end")
    f.edge("fpa_usb","end")
    f.edge("fpa_cfg","end")
    f.edge("com_drv","end")
    f.edge("com_cfg","end")
    return f.render()


def fc_test_failure():
    f = SVGFlowchart(660, "6.3  Test Execution Failure")
    cx = 330
    f.term("start","Test execution failure", cx, 55)
    f.decision("scope","All stations or one station?", cx, 120)
    f.proc("all","All stations — system issue", 180, 200)
    f.proc("one","Single station — fixture issue", 480, 200)

    f.decision("which","Which test fails?", 180, 280)
    f.proc("volt","Voltage / Current test", 60, 360)
    f.proc("flash","Firmware flash", 180, 360)
    f.proc("ver","Version / serial test", 300, 360)

    f.action("fix_v","Check DUT power\nVerify reference applied", 60, 440, C_ACTION, C_LTGREEN)
    f.action("fix_f","Check FPA USB\nVerify firmware files exist", 180, 440, C_ACTION, C_LTGREEN)
    f.action("fix_s","Check COM config\nVerify DUT firmware running", 300, 440, C_ACTION, C_LTGREEN)

    f.proc("stn","Check station COM port\nVerify DUT in correct socket", 480, 280)
    f.action("log","Review program_log.txt\nfor station-specific ERROR", 480, 360, C_WARN)

    f.decision("err_type","Timeout or decode error?", 480, 440)
    f.action("t_fix","Increase TEST_TIMEOUT\nCheck DUT response time", 400, 520, C_ACTION, C_LTGREEN)
    f.action("d_fix","Verify firmware version\nCheck packet length", 560, 520, C_ACTION, C_LTGREEN)

    f.edge("start","scope")
    f.edge("scope","all","All")
    f.edge("scope","one","One")
    f.edge("all","which")
    f.edge("which","volt","V/I")
    f.edge("which","flash","Flash")
    f.edge("which","ver","Serial")
    f.edge("volt","fix_v")
    f.edge("flash","fix_f")
    f.edge("ver","fix_s")
    f.edge("one","stn")
    f.edge("stn","log")
    f.edge("log","err_type")
    f.edge("err_type","t_fix","Timeout")
    f.edge("err_type","d_fix","Decode")
    return f.render()


def fc_comm_failure():
    f = SVGFlowchart(660, "6.4  Communication Failure")
    cx = 330
    f.term("start","Communication failure", cx, 55)
    f.decision("proto","Protocol type?", cx, 125)

    f.proc("aa","0xAA frame 9600 baud\n(LTCT / WC serial test)", 130, 200)
    f.proc("dlms","0x7E DLMS 19200 baud\n(FG23 firmware version)", 330, 200)
    f.proc("wire","Wirepas UART\n(IMG provisioning)", 530, 200)

    f.decision("aa_ok","Start byte 0xAA\nseen in log?", 130, 290)
    f.action("aa_hw","Cable issue or\nwrong COM port", 60, 370, C_WARN)
    f.action("aa_len","Check fixed_packet_len\nmatches expected response", 200, 370, C_ACTION, C_LTGREEN)

    f.decision("dlms_ok","Valid packet\nreceived?", 330, 290)
    f.action("dlms_fw","Wrong meter firmware\nDLMS frame mismatch", 260, 370, C_WARN)
    f.action("dlms_q","Check queue.get()\ntimeout value", 400, 370, C_ACTION, C_LTGREEN)

    f.action("wire_fix","Verify DUT powered\nand in factory mode\nCheck Wirepas radio init", 530, 290, C_ACTION, C_LTGREEN)

    f.term("end","Communication restored", cx, 460, C_ACTION)

    f.edge("start","proto")
    f.edge("proto","aa","0xAA")
    f.edge("proto","dlms","DLMS")
    f.edge("proto","wire","Wirepas")
    f.edge("aa","aa_ok")
    f.edge("aa_ok","aa_hw","No")
    f.edge("aa_ok","aa_len","Yes")
    f.edge("dlms","dlms_ok")
    f.edge("dlms_ok","dlms_fw","No")
    f.edge("dlms_ok","dlms_q","Yes")
    f.edge("wire","wire_fix")
    f.edge("aa_hw","end")
    f.edge("aa_len","end")
    f.edge("dlms_fw","end")
    f.edge("dlms_q","end")
    f.edge("wire_fix","end")
    return f.render()


def fc_file_failure():
    f = SVGFlowchart(540, "6.5  Database / File Failure")
    cx = 270
    f.term("start","Excel / file issue reported", cx, 55)
    f.decision("etype","Error type?", cx, 125)

    f.proc("bzip","BadZipFile\n(corruption)", 110, 200)
    f.proc("fnf","FileNotFoundError\n(disk / permissions)", 270, 200)
    f.proc("perm","PermissionError\n(file open in Excel)", 430, 200)

    f.action("bzip_fix","App auto-renames to .corrupted\nNew file created\nOpen .corrupted in Excel Repair", 110, 290, C_ACTION, C_LTGREEN)
    f.action("fnf_fix","Run app as Administrator\nFree disk space > 500 MB", 270, 290, C_ACTION, C_LTGREEN)
    f.action("perm_fix","Close all Excel windows\nDo not open result file\nduring active test run", 430, 290, C_ACTION, C_LTGREEN)

    f.decision("ok","File accessible?", cx, 380)
    f.warn("esc","Escalate — check disk health\nrun chkdsk", cx, 460)
    f.term("end","Resume testing", cx, 460, C_ACTION)

    f.edge("start","etype")
    f.edge("etype","bzip","BadZip")
    f.edge("etype","fnf","NotFound")
    f.edge("etype","perm","Permission")
    f.edge("bzip","bzip_fix")
    f.edge("fnf","fnf_fix")
    f.edge("perm","perm_fix")
    f.edge("bzip_fix","ok")
    f.edge("fnf_fix","ok")
    f.edge("perm_fix","ok")
    f.edge("ok","esc","No")
    f.edge("ok","end","Yes")
    return f.render()


def fc_production_line():
    f = SVGFlowchart(620, "6.6  Production Line Failure")
    cx = 310
    f.term("start","Production line stoppage", cx, 55)
    f.decision("scope","How many jigs affected?", cx, 125)
    f.proc("all","All jigs — infra issue", 170, 200)
    f.proc("one","Single jig", 450, 200)

    f.action("infra","Check power / USB hub\nCheck Windows event log\nRestart PC", 170, 285, C_WARN)
    f.decision("restart","Can app be restarted?", 450, 285)

    f.action("res","Restart app\nVerify COM ports in\nDevice Manager", 380, 370, C_ACTION, C_LTGREEN)
    f.warn("hw","Hardware fault\nCheck DAQ USB / FPA USB\nSwap cable or DAQ device", 530, 370)

    f.decision("pass","Tests passing?", cx, 460)
    f.action("resume","Resume production\nNote incident in shift log", 180, 545, C_ACTION, C_LTGREEN)
    f.warn("esc","Escalate to SW/HW team\nCapture all log files", 440, 545)

    f.edge("start","scope")
    f.edge("scope","all","All")
    f.edge("scope","one","One")
    f.edge("all","infra")
    f.edge("infra","pass")
    f.edge("one","restart")
    f.edge("restart","res","Yes")
    f.edge("restart","hw","No")
    f.edge("res","pass")
    f.edge("hw","pass")
    f.edge("pass","resume","Yes")
    f.edge("pass","esc","No")
    return f.render()


CHARTS = {
    "fc_app":    fc_app_not_launching(),
    "fc_hw":     fc_hw_not_detected(),
    "fc_test":   fc_test_failure(),
    "fc_comm":   fc_comm_failure(),
    "fc_file":   fc_file_failure(),
    "fc_prod":   fc_production_line(),
}

if __name__ == "__main__":
    import os
    out = "/Users/lalit.tak/Documents/Workspace/Prod_tool_troubleshoot_guide/flowcharts"
    os.makedirs(out, exist_ok=True)
    for name, svg in CHARTS.items():
        path = os.path.join(out, f"{name}.svg")
        with open(path, "w") as f:
            f.write(svg)
        print(f"Written: {path}")
    print("All flowcharts generated.")
