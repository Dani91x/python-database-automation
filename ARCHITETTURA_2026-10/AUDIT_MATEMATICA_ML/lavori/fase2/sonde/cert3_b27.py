import sys
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from value_engine.poisson_total import lam_from_prematch
from value_engine.devig import devig_pair
nan = float("nan")
for args in [("over", 2, nan), ("under", 2, nan), ("over", 2, 0.5)]:
    try:
        print("lam_from_prematch", args, "->", lam_from_prematch(*args))
    except Exception as e:
        print("lam_from_prematch", args, "EXC", type(e).__name__, e)
print("devig_pair(2.0, 1.0) =", devig_pair(2.0, 1.0), " devig_pair(2.0,0) =", devig_pair(2.0, 0), " devig_pair(2.0,nan)=", devig_pair(2.0, nan))
print("devig_pair(1.9,1.9)=", devig_pair(1.9, 1.9))
