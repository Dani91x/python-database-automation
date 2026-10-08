"""M7 - due misure di laboratorio di rete (nessun codice di produzione, nessuna chiave, nessun dato scritto).

A) canale locale: giro WebSocket su 127.0.0.1 nello stesso processo (server + client della libreria
   `websockets` della .venv), payload ladder-like di ~1,3 KB (3 selezioni x 10 livelli x back/lay) serializzato con json.dumps come fa
   Betfair/stream/local_channel.py:620-672 (publish). Si misura: costo di json.dumps, e il tempo da
   «send sul server» a «ricevuto dal client» con 2000 messaggi a cadenza 5 ms. E' un LIMITE INFERIORE
   del canale vero (stesso processo, nessun altro carico), non la misura del canale di produzione.
B) rete verso il cloud: per l'host Supabase del progetto, DNS, connessione TCP, handshake TLS e poi 40
   richieste `GET /rest/v1/` SENZA chiave sulla stessa connessione (rispondono 401/404: misurano il
   giro di rete + gateway, NON una query). Il costo di una query vera e' questo + il tempo di esecuzione
   in Postgres (pg_stat_statements: vedi 07_MISURE_OGGI.md, sezione M7).
Uso: python -I m07_lab_rete.py <host_supabase>
"""
import asyncio, json, socket, ssl, sys, time, http.client

HOST = sys.argv[1] if len(sys.argv) > 1 else "dqbwaocvlzbxfrpacsac.supabase.co"


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def riass(v, scala=1e3, unita="ms"):
    return "n=%d p50=%.3f p95=%.3f p99=%.3f max=%.3f %s" % (
        len(v), pct(v, .5) * scala, pct(v, .95) * scala, pct(v, .99) * scala, max(v) * scala, unita)


def payload(i):
    liv = lambda base: [[round(base + k * 0.01, 2), 100.5 + k] for k in range(10)]
    return {"event_id": "35760084", "market_id": "1.2345678", "market_type": "MATCH_ODDS", "market_name": "Match Odds",
            "status": "OPEN", "ladder": {"seq": i, "selections": [
                {"selection_id": 1000 + s, "name": "Sel %d" % s, "b": liv(1.5 + s), "l": liv(1.6 + s), "ltp": 1.55, "tv": 12345.6}
                for s in range(3)]}}


async def lab_ws():
    import websockets
    from websockets.asyncio.server import serve
    from websockets.asyncio.client import connect
    clients = set()
    attesi = {}
    ser = []

    async def handler(ws):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with serve(handler, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        async with connect("ws://127.0.0.1:%d" % port) as cli:
            while not clients:
                await asyncio.sleep(0.01)
            lat = []
            ws = next(iter(clients))
            for i in range(2000):
                dati = {"t": "ladder", "d": payload(i)}   # costruzione fuori dalla misura
                t0 = time.perf_counter()
                text = json.dumps(dati, default=str)
                t1 = time.perf_counter()
                ser.append(t1 - t0)
                await ws.send(text)
                got = await cli.recv()
                lat.append(time.perf_counter() - t1)
                await asyncio.sleep(0.005)
    print("A) payload %d byte; json.dumps: %s" % (len(text), riass(ser, 1e6, "us")))
    print("A) giro send->recv su loopback (stesso processo): %s" % riass(lat))


def lab_rete():
    t = time.perf_counter(); ip = socket.getaddrinfo(HOST, 443, socket.AF_INET)[0][4][0]; t_dns = time.perf_counter() - t
    t = time.perf_counter(); s = socket.create_connection((ip, 443), timeout=5); t_tcp = time.perf_counter() - t
    ctx = ssl.create_default_context()
    t = time.perf_counter(); ss = ctx.wrap_socket(s, server_hostname=HOST); t_tls = time.perf_counter() - t
    ss.close()
    print("B) %s -> %s: DNS %.1f ms, TCP connect %.1f ms, TLS handshake %.1f ms" % (HOST, ip, t_dns * 1e3, t_tcp * 1e3, t_tls * 1e3))
    c = http.client.HTTPSConnection(HOST, timeout=10)
    lat, stati = [], {}
    for i in range(40):
        t = time.perf_counter()
        c.request("GET", "/rest/v1/", headers={"Connection": "keep-alive"})
        r = c.getresponse(); r.read()
        lat.append(time.perf_counter() - t)
        stati[r.status] = stati.get(r.status, 0) + 1
        time.sleep(0.05)
    c.close()
    print("B) GET /rest/v1/ senza chiave, connessione riusata: stati %s ; %s ; prima richiesta %.1f ms" % (
        stati, riass(lat[1:]), lat[0] * 1e3))


asyncio.run(lab_ws())
lab_rete()
