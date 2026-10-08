import json, sys, difflib
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
for k in a:
    if a[k] != b.get(k):
        print("DIVERSO:", k)
print("frames", len(a["frames"]), len(b["frames"]))
fa = [json.dumps(x) for x in a["frames"]]; fb = [json.dumps(x) for x in b["frames"]]
for l in difflib.unified_diff(fa, fb, "fixture", "rigenerata", n=2, lineterm=""):
    print(l[:400])
