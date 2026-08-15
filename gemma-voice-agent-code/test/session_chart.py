"""ADK session backends by client location - two stacked panels, one image."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#1a1a19"
INK2 = "#5f5e56"
GRID = "#e5e4df"
ORDER = ["in-memory", "SQL (SQLite via ADK)", "SQL (Cloud SQL via ADK)", "Agent Engine (ADK)"]
COLORS = {"in-memory": "#2a78d6", "SQL (SQLite via ADK)": "#eb6834",
          "SQL (Cloud SQL via ADK)": "#4a3aa7", "Agent Engine (ADK)": "#1baf7a"}

positions = [
    "Same-region container\n(us-central1)",
    "Cross-region container\n(europe-west1)",
    "Laptop over VPN\n(far from region)",
]

panels = [
    ("New conversation: one session create", {
        "in-memory": [0.0002, 0.0002, 0.0002],
        "SQL (SQLite via ADK)": [0.004, 0.004, 0.004],
        "SQL (Cloud SQL via ADK)": [0.026, 0.96, 0.77],
        "Agent Engine (ADK)": [0.27, 0.93, 1.98],
    }, {
        "in-memory": ["~0 s", "~0 s", "~0 s"],
        "SQL (SQLite via ADK)": ["0.004 s", "0.004 s", "0.004 s"],
        "SQL (Cloud SQL via ADK)": ["0.026 s", "0.96 s", "0.77 s"],
        "Agent Engine (ADK)": ["0.27 s", "0.93 s", "2.0 s"],
    }),
    ("Continuing turn: one get + append", {
        "in-memory": [0.0002, 0.0002, 0.0002],
        "SQL (SQLite via ADK)": [0.008, 0.010, 0.009],
        "SQL (Cloud SQL via ADK)": [0.056, 2.018, 1.623],
        "Agent Engine (ADK)": [0.31, 1.512, 3.371],
    }, {
        "in-memory": ["~0 s", "~0 s", "~0 s"],
        "SQL (SQLite via ADK)": ["0.008 s", "0.010 s", "0.009 s"],
        "SQL (Cloud SQL via ADK)": ["0.056 s", "2.0 s", "1.6 s"],
        "Agent Engine (ADK)": ["0.31 s", "1.5 s", "3.4 s"],
    }),
]

bar_h = 0.19
gap = 0.025
ys = range(len(positions))
fig, axes = plt.subplots(2, 1, figsize=(8.8, 9.2), dpi=200)
fig.patch.set_facecolor(SURFACE)

for ax, (subtitle, data, labels) in zip(axes, panels):
    ax.set_facecolor(SURFACE)
    for i, backend in enumerate(ORDER):
        vals = data[backend]
        offs = [y + (i - 1.5) * (bar_h + gap) for y in ys]
        ax.barh(offs, vals, height=bar_h, color=COLORS[backend], label=backend)
        for y, v, lab in zip(offs, vals, labels[backend]):
            ax.text(max(v, 0.01) + 0.05, y, lab, va="center", ha="left",
                    fontsize=8.5, color=INK)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(positions, fontsize=9.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 4.2)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="x", colors=INK2, labelsize=8.5)
    ax.tick_params(axis="y", length=0)
    ax.set_title(subtitle, fontsize=11, color=INK, loc="left", pad=12)

axes[1].set_xlabel("seconds (median of 5; backends in us-central1; warmed backends, fresh client)",
                   fontsize=8.5, color=INK2)
for ax in axes:
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 1.0), frameon=False,
              fontsize=9, labelcolor=INK)
fig.suptitle("ADK session backends by client location", fontsize=13, color=INK,
             x=0.02, ha="left", y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.965))
fig.savefig(Path(__file__).with_name("session-backends.png"),
            facecolor=SURFACE, bbox_inches="tight")
print("saved")
