# TEMPORARY diagnostic plugin — hunting the ~5MB/min heap leak on warehouse-duckdb.
# Logs, once a minute, the process RSS and the Python object types whose gc count
# GREW since the last sample. The type that climbs monotonically across samples is
# the leak. Lightweight: one gc.get_objects() sweep/min, no per-allocation tracking.
# REMOVE after diagnosis (next deploy).
from datasette import hookimpl
import gc, threading, time, sys, collections, re


def _rss_mb():
    try:
        s = open("/proc/self/status").read()
        return int(re.search(r"VmRSS:\s*(\d+)", s).group(1)) // 1024
    except Exception:
        return -1


@hookimpl
def startup(datasette):
    def loop():
        base = None
        while True:
            time.sleep(60)
            try:
                gc.collect()
                c = collections.Counter(type(o).__name__ for o in gc.get_objects())
                line = "GCPROBE rss=%dMB total_objs=%d" % (_rss_mb(), sum(c.values()))
                if base is not None:
                    grow = sorted(((c[k] - base.get(k, 0), k) for k in c), reverse=True)[:15]
                    line += " | grew: " + " ".join("%s+%d" % (k, d) for d, k in grow if d > 5)
                print(line, file=sys.stderr, flush=True)
                base = c
            except Exception as e:
                print("GCPROBE error: %r" % e, file=sys.stderr, flush=True)

    threading.Thread(target=loop, daemon=True, name="gcprobe").start()
