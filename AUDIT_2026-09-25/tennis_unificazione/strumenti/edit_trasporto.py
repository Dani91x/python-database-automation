"""Trasporto del banco: Safe tennis sul canale (F8). Lanciato una volta."""
import io

p = "Betfair/stream/backtest/trasporto.py"
s = io.open(p, encoding="utf-8").read()


def sost(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:90])
    s = s.replace(old, new)


sost('''    "omega": ("omega", "OMEGA_ORDINI_VIA_CANALE"),
}
''', '''    "omega": ("omega", "OMEGA_ORDINI_VIA_CANALE"),
    # 25/09 (F8): Safe tennis sul canale 47332 del runner TENNIS (motore con
    # l'esecutore tennis, ``porta_banco.PortaBanco(sport="tennis")``)
    "safe_tennis": ("safe_tennis", "SAFE_TENNIS_ORDINI_VIA_CANALE"),
}

#: lo sport del runner di ogni attore (quale motore, quale porta del bot)
SPORT_ATTORE: Dict[str, str] = {"safe": "calcio", "omega": "calcio",
                                "safe_tennis": "tennis"}
''')
sost('''    "safe_tennis": "F8 non fatta: canale 47332 + controllo su tennis_live_follow; ref "
                   "safe-t<id> diverso dal prefisso safe_tennis- preteso dal motore",
}
''', '''}
''')
sost('''    modo = "LIVE" if str(getattr(strategia, "mode", "live")) == "live" else "PAPER"
    pb = PortaBanco(motore.quadro, strategia, attore=st["attore"], modo_processo=modo)
''', '''    modo = "LIVE" if str(getattr(strategia, "mode", "live")) == "live" else "PAPER"
    sport = SPORT_ATTORE.get(str(st["attore"]), "calcio")
    pb = PortaBanco(motore.quadro, strategia, attore=st["attore"], modo_processo=modo,
                    sport=sport)
''')
sost('''        from ...safe_strategy import porta_ordini as SPO

        client = SPO.PortaCanale(porta_ws=0, attore="safe", sport="calcio",
                                 connetti=pb.connetti, token_fn=lambda: TOKEN_BANCO)
        st["_ripristina"] = ("safe", SPO._PORTE.get("calcio"))
        SPO._PORTE["calcio"] = client
''', '''        from ...safe_strategy import porta_ordini as SPO

        client = SPO.PortaCanale(porta_ws=0, attore=st["attore"], sport=sport,
                                 connetti=pb.connetti, token_fn=lambda: TOKEN_BANCO)
        st["_ripristina"] = ("safe:" + sport, SPO._PORTE.get(sport))
        SPO._PORTE[sport] = client
''')
sost('''        else:
            from ...safe_strategy import porta_ordini as SPO

            if prima is None:
                SPO._PORTE.pop("calcio", None)
            else:
                SPO._PORTE["calcio"] = prima
''', '''        else:
            from ...safe_strategy import porta_ordini as SPO

            sport = chi.split(":", 1)[1] if ":" in chi else "calcio"
            if prima is None:
                SPO._PORTE.pop(sport, None)
            else:
                SPO._PORTE[sport] = prima
''')
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
