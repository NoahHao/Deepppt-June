import sys
import os
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)

from mirror_fill import MirrorFiller

src = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "projects", "huawei_solution_ppt169_20260602",
    "exports", "huawei_solution_20260602_163633.pptx"
)

print("=" * 70)
print("TEST: MirrorFiller.inspect()")
print("=" * 70)

filler = MirrorFiller(src, slide_num=1, layout="left_right")

result = filler.inspect()
print(f"\nInspect result type: {type(result)}")
print(f"Inspect result:/n{result}")

print("\n" + "=" * 70)
print("Filler info:")
print(filler.info())

