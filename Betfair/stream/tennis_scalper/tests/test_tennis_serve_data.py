"""Lo stub dati serve degrada da solo quando i dati non ci sono."""

from Betfair.stream.tennis_scalper import tennis_serve_data as sd


def test_no_csv_returns_none(monkeypatch):
    monkeypatch.setattr(sd, "_cache", None)
    monkeypatch.setattr(sd, "_CSV", "/percorso/inesistente/serve_data.csv")
    ph, pa = sd.get_serve_probs("Papoe", "Midon")
    assert ph is None and pa is None


def test_none_name():
    assert sd.get_serve_prob(None) is None


def test_reads_csv(tmp_path, monkeypatch):
    csv = tmp_path / "serve_data.csv"
    csv.write_text("name,serve_win_pct\nJannik Sinner,68\nHolger Rune,63\n",
                   encoding="utf-8")
    monkeypatch.setattr(sd, "_cache", None)
    monkeypatch.setattr(sd, "_CSV", str(csv))
    ph, pa = sd.get_serve_probs("jannik sinner", "holger rune")
    assert ph == 0.68
    assert pa == 0.63
