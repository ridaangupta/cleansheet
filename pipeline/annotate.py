"""Click board corners on keyframes of a real clip, then track them across every frame.

Usage: python pipeline/annotate.py footage/<clip>.mp4 [--boards footage/<clip>.boards.json]

Keys (focus the video window):
  d / a        next / previous frame        l / j    +10 / -10 frames
  n            new board: click its 4 corners TL, TR, BR, BL on the current frame
  k            re-key the selected board on the current frame (click 4 corners)
  x            delete the selected board's keyframe on the current frame
  tab          select the next board         DEL      delete the selected board
  t            track all boards (optical flow) and save
  s            save                          q        save and quit       esc  quit without saving

Rows (a whole side of perimeter boards as one quad, split into equal boards by composite.py):
  + / -        more / fewer boards in the selected row (1 = a single board, no split)
  [ / ]        extend the selected row by a quarter of its length to the left / right
  0            reset the extension

The grey margin around the frame is clickable, for corners just off screen.

Tips for single boards: key a board when it first appears, when it leaves, and every 1-2 s
during fast pans. Then press t and scrub to check the tracked quads (drawn thinner).

Tips for rows: click a visible stretch of the row, with the left and right edges on board seams
you can find again later (the top and bottom edges follow the boards). Set + / - so each split
board is about 4:1 like the brand art, and [ / ] so the row covers the whole side. One keyframe
is enough: t tracks it across the clip. If it drifts, add a keyframe with k at the frame where
it's worst, clicking the same seams again.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

import boards as boards_io
from videoio import probe, read_frames

WINDOW = "cleansheet annotate"
MAX_VIEW_W = 1400
MARGIN = 0.12  # clickable border around the frame, as a fraction of its width/height
EXTEND_STEP = 0.25


class Annotator:
    def __init__(self, video: Path, boards_path: Path):
        self.video = video
        self.boards_path = boards_path
        print("loading frames...")
        self.frames = list(read_frames(video))
        w, h, fps, _ = probe(video)
        self.mx, self.my = int(w * MARGIN), int(h * MARGIN)
        self.scale = min(1.0, MAX_VIEW_W / (w + 2 * self.mx))
        if boards_path.exists():
            self.data = boards_io.load(boards_path)
        else:
            self.data = {"video": video.name, "width": w, "height": h, "fps": fps,
                         "frame_count": len(self.frames), "boards": []}
        self.i = 0
        self.sel = 0 if self.data["boards"] else -1
        self.clicks: list[tuple[float, float]] = []
        self.pending: str | None = None  # "new" or "rekey" while collecting clicks

    # -- editing -------------------------------------------------------------

    def board(self) -> dict | None:
        return self.data["boards"][self.sel] if 0 <= self.sel < len(self.data["boards"]) else None

    def set_keyframe(self, board: dict, quad: list[tuple[float, float]]) -> None:
        board.setdefault("keyframes", {})[str(self.i)] = [[round(x, 2), round(y, 2)] for x, y in quad]
        board.pop("frames", None)  # tracked frames are stale now

    def on_mouse(self, event, x, y, *_):
        if event != cv2.EVENT_LBUTTONDOWN or self.pending is None:
            return
        self.clicks.append((x / self.scale - self.mx, y / self.scale - self.my))
        if len(self.clicks) < 4:
            return
        if self.pending == "new":
            ids = {b["id"] for b in self.data["boards"]}
            n = len(self.data["boards"]) + 1
            while f"b{n:02d}" in ids:
                n += 1
            self.data["boards"].append({"id": f"b{n:02d}", "kind": "board", "keyframes": {}})
            self.sel = len(self.data["boards"]) - 1
        self.set_keyframe(self.board(), self.clicks)
        self.clicks, self.pending = [], None

    def save(self) -> None:
        boards_io.save(self.boards_path, self.data)
        print(f"saved {self.boards_path}")

    # -- drawing -------------------------------------------------------------

    def draw(self) -> np.ndarray:
        img = cv2.copyMakeBorder(self.frames[self.i], self.my, self.my, self.mx, self.mx,
                                 cv2.BORDER_CONSTANT, value=(60, 60, 60))
        offset = np.float32([self.mx, self.my])
        for k, board in enumerate(self.data["boards"]):
            kfs = board.get("keyframes", {})
            quads = boards_io.resolve(board)
            q = quads.get(self.i)
            if q is None:
                continue
            is_key = str(self.i) in kfs
            color = (0, 255, 255) if k == self.sel else (0, 200, 0)
            split = int(board.get("split", 1))
            if split > 1:
                # Preview the individual boards the row will be split into, extension included.
                for part in boards_io.row_quads(q, split, tuple(board.get("extend", (0.0, 0.0)))):
                    cv2.polylines(img, [(part + offset).astype(np.int32)], True, (255, 0, 255), 1, cv2.LINE_AA)
            cv2.polylines(img, [(q + offset).astype(np.int32)], True, color, 3 if is_key else 1, cv2.LINE_AA)
            label = board["id"] + (f" row x{split}" if split > 1 else "") + (" [key]" if is_key else "")
            cv2.putText(img, label, tuple((q[0] + offset).astype(int) + [0, -6]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
        for x, y in self.clicks:
            cv2.circle(img, (int(x + self.mx), int(y + self.my)), 5, (0, 0, 255), -1)
        if self.scale != 1.0:
            img = cv2.resize(img, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        b = self.board()
        status = f"frame {self.i}/{len(self.frames) - 1}   selected {b['id'] if b else '-'}"
        if self.pending:
            status += f"   click corner {len(self.clicks) + 1}/4 (TL, TR, BR, BL)"
        cv2.rectangle(img, (0, 0), (img.shape[1], 28), (0, 0, 0), -1)
        cv2.putText(img, status, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        return img

    # -- loop ----------------------------------------------------------------

    def run(self) -> None:
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(WINDOW, self.on_mouse)
        last = len(self.frames) - 1
        while True:
            cv2.imshow(WINDOW, self.draw())
            key = cv2.waitKey(30)
            if key == -1:
                continue
            ch = chr(key & 0xFF) if (key & 0xFF) < 128 else ""
            if key == 27:
                return
            if ch == "q":
                self.save()
                return
            if self.pending and ch not in ("d", "a", "l", "j"):
                continue  # finish clicking first
            if ch == "d":
                self.i = min(last, self.i + 1)
            elif ch == "a":
                self.i = max(0, self.i - 1)
            elif ch == "l":
                self.i = min(last, self.i + 10)
            elif ch == "j":
                self.i = max(0, self.i - 10)
            elif ch == "n":
                self.pending, self.clicks = "new", []
            elif ch == "k" and self.board():
                self.pending, self.clicks = "rekey", []
            elif ch in ("+", "=", "-") and self.board():
                b = self.board()
                b["split"] = max(1, int(b.get("split", 1)) + (-1 if ch == "-" else 1))
                if b["split"] == 1:
                    b.pop("split")
                    b.pop("extend", None)
            elif ch in ("[", "]") and self.board() and int(self.board().get("split", 1)) > 1:
                ext = list(self.board().get("extend", [0.0, 0.0]))
                ext[0 if ch == "[" else 1] += EXTEND_STEP
                self.board()["extend"] = ext
            elif ch == "0" and self.board():
                self.board().pop("extend", None)
            elif ch == "x" and self.board():
                self.board().get("keyframes", {}).pop(str(self.i), None)
                self.board().pop("frames", None)
            elif key == 9 and self.data["boards"]:
                self.sel = (self.sel + 1) % len(self.data["boards"])
            elif key in (8, 127) and self.board():
                del self.data["boards"][self.sel]
                self.sel = min(self.sel, len(self.data["boards"]) - 1)
            elif ch == "t":
                print("tracking...")
                report = boards_io.densify_all(self.video, self.data)
                for board_id, result in report.items():
                    if isinstance(result, str):
                        note = f" {result}"
                    else:
                        note = f", {result} segment(s) fell back to linear" if result else ""
                    print(f"  {board_id}: tracked{note}")
                self.save()
            elif ch == "s":
                self.save()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--boards", type=Path)
    args = ap.parse_args()
    Annotator(args.video, args.boards or args.video.with_suffix(".boards.json")).run()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
