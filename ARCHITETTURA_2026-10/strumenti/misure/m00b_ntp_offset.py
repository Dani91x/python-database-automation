"""Scarto dell'orologio del PC contro NTP (sola lettura: 1 pacchetto UDP SNTP per server, 5 prove).
Serve per dire quanto valgono i confronti fra istanti locali e `pt` di Betfair.
offset = ((t1-t0)+(t2-t3))/2 ; positivo = il PC e' INDIETRO rispetto al server.
Uso: python -I m00b_ntp_offset.py
"""
import socket, struct, time

SERVERS = ["time.windows.com", "pool.ntp.org", "time.cloudflare.com"]
EPOCH = 2208988800


def prova(srv):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    pkt = b'\x1b' + 47 * b'\0'
    t0 = time.time()
    s.sendto(pkt, (srv, 123))
    data, _ = s.recvfrom(48)
    t3 = time.time()
    u = struct.unpack('!12I', data)
    t1 = u[8] - EPOCH + u[9] / 2 ** 32
    t2 = u[10] - EPOCH + u[11] / 2 ** 32
    return ((t1 - t0) + (t2 - t3)) / 2 * 1000, (t3 - t0) * 1000


for srv in SERVERS:
    off, rtt = [], []
    for _ in range(5):
        try:
            o, r = prova(srv)
            off.append(o); rtt.append(r)
        except Exception as e:  # noqa
            print(srv, "KO", type(e).__name__, e)
            break
        time.sleep(0.3)
    if off:
        print("%s: offset ms (PC indietro se >0) %s | RTT ms %s" % (
            srv, ["%.0f" % x for x in off], ["%.0f" % x for x in rtt]))
