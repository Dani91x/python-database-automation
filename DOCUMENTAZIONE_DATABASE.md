# Documentazione Schema Database - Automazione Calcio

Questo documento fornisce una spiegazione dettagliata di ogni tabella presente nel database, inclusi i tipi di dati, le colonne e il formato dei dati.

---

## 1. fixture_predictions
Contiene i pronostici generati dall'algoritmo o recuperati dall'API per ogni partita (fixture).

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `fixture_id` | `INTEGER` (PK) | ID unico della partita (API-Football) |
| `league_id` | `INTEGER` | ID della competizione |
| `league_name` | `TEXT` | Nome della competizione |
| `season_year` | `INTEGER` | Anno della stagione |
| `fixture_date` | `TIMESTAMP` | Data e ora della partita (UTC) |
| `home_team_id` | `INTEGER` | ID della squadra di casa |
| `home_team_name` | `TEXT` | Nome della squadra di casa |
| `away_team_id` | `INTEGER` | ID della squadra in trasferta |
| `away_team_name` | `TEXT` | Nome della squadra in trasferta |
| `status` | `TEXT` | Stato del pronostico (es. 'ok', 'empty', 'no_coverage') |
| `winner_team_id` | `INTEGER` | ID della squadra favorita per la vittoria |
| `winner_name` | `TEXT` | Nome della squadra favorita |
| `winner_comment` | `TEXT` | Commento descrittivo sulla squadra favorita |
| `win_or_draw` | `BOOLEAN` | Indica se la previsione include il pareggio |
| `advice` | `TEXT` | Consiglio testuale (es. "Home or draw", "Under 3.5") |
| `percent_home` | `FLOAT` | Probabilità vittoria casa (%) |
| `percent_draw` | `FLOAT` | Probabilità pareggio (%) |
| `percent_away` | `FLOAT` | Probabilità vittoria trasferta (%) |
| `under_over_line` | `TEXT` | Soglia Under/Over suggerita |
| `goals_home_line` | `TEXT` | **xG Predict**: Gol previsti per la squadra di casa |
| `goals_away_line` | `TEXT` | **xG Predict**: Gol previsti per la squadra in trasferta |
| `flat_summary` | `JSONB` | Riepilogo piatto delle statistiche principali |
| `raw_json` | `JSONB` | Risposta JSON originale dell'API |
| `updated_at` | `TIMESTAMP` | Ultimo aggiornamento del record |

---

## 2. injuries
Elenco degli infortuni e dei giocatori non disponibili per specifici match.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `league_id` | `INTEGER` | ID della competizione |
| `season_year` | `INTEGER` | Anno della stagione |
| `fixture_id` | `INTEGER` | ID della partita correlata |
| `fixture_date` | `TIMESTAMP` | Data del match |
| `player_id` | `INTEGER` | ID unico del giocatore |
| `player_name` | `TEXT` | Nome del giocatore |
| `player_age` | `INTEGER` | Età del giocatore |
| `player_nationality` | `TEXT` | Nazionalità del giocatore |
| `team_id` | `INTEGER` | ID della squadra |
| `team_name` | `TEXT` | Nome della squadra |
| `type` | `TEXT` | Tipo di assenza (es. "Injury", "Suspension") |
| `reason` | `TEXT` | Motivo specifico (es. "Knee Injury", "Red Card") |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 3. match_events
Eventi salienti accaduti durante la partita (gol, ammonizioni, sostituzioni).

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `fixture_id` | `INTEGER` | ID della partita |
| `team_id` | `INTEGER` | ID della squadra che ha generato l'evento |
| `team_name` | `TEXT` | Nome della squadra |
| `player_id` | `INTEGER` | ID del giocatore coinvolto |
| `player_name` | `TEXT` | Nome del giocatore |
| `assist_id` | `INTEGER` | ID del giocatore dell'assist (se presente) |
| `assist_name` | `TEXT` | Nome del giocatore dell'assist |
| `event_type` | `TEXT` | Tipo di evento (Goal, Card, Subst, Var) |
| `detail` | `TEXT` | Dettaglio (es. "Yellow Card", "Normal Goal") |
| `comments` | `TEXT` | Commenti aggiuntivi |
| `minute` | `INTEGER` | Minuto dell'evento |
| `minute_extra` | `INTEGER` | Minuti di recupero |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 4. match_lineups
Formazioni ufficiali, titolari, panchina e allenatori.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `fixture_id` | `INTEGER` | ID della partita |
| `team_id` | `INTEGER` | ID della squadra |
| `team_name` | `TEXT` | Nome della squadra |
| `coach_id` | `INTEGER` | ID dell'allenatore |
| `coach_name` | `TEXT` | Nome dell'allenatore |
| `player_id` | `INTEGER` | ID del giocatore |
| `player_name` | `TEXT` | Nome del giocatore |
| `player_number` | `INTEGER` | Numero di maglia |
| `position` | `TEXT` | Posizione (G, D, M, F) |
| `grid` | `TEXT` | Posizione sulla griglia tattica (es. "1:1") |
| `is_starter` | `BOOLEAN` | True se titolare, False se riserva |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 5. match_odds
Dati sulle quote scommesse recuperati dai bookmaker.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `fixture_id` | `INTEGER` | ID della partita |
| `bookmaker_id` | `INTEGER` | ID del bookmaker |
| `bookmaker_name` | `TEXT` | Nome del bookmaker (es. "Betfair") |
| `market_key` | `TEXT` | Chiave del mercato (es. "1", "Under/Over") |
| `market_name` | `TEXT` | Nome del mercato |
| `label` | `TEXT` | Etichetta dell'esito (es. "Home", "Over 2.5") |
| `odd_value` | `FLOAT` | Valore della quota |
| `snapshot_type` | `TEXT` | Fonte (es. "api_football") |
| `snapshot_time` | `TIMESTAMP` | Momento della rilevazione |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 6. match_player_stats
Statistiche individuali dettagliate per ogni giocatore nel match.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `fixture_id` | `INTEGER` | ID della partita |
| `player_id` | `INTEGER` | ID del giocatore |
| `player_name` | `TEXT` | Nome del giocatore |
| `team_id` | `INTEGER` | ID della squadra |
| `minutes` | `INTEGER` | Minuti giocati |
| `rating` | `TEXT` | Voto/Rating della prestazione |
| `shots_total` | `INTEGER` | Tiri totali |
| `shots_on` | `INTEGER` | Tiri in porta |
| `goals_total` | `INTEGER` | Gol segnati |
| `assists_total` | `INTEGER` | Assist effettuati |
| `passes_total` | `INTEGER` | Passaggi totali |
| `passes_key` | `INTEGER` | Passaggi chiave |
| `passes_accurate` | `INTEGER` | Precisione passaggi (%) |
| `tackles_total` | `INTEGER` | Contrasti |
| `interceptions` | `INTEGER` | Intercettazioni |
| `duels_total` | `INTEGER` | Duelli totali |
| `duels_won` | `INTEGER` | Duelli vinti |
| `dribbles_attempts` | `INTEGER` | Tentativi di dribbling |
| `dribbles_success` | `INTEGER` | Dribbling riusciti |
| `fouls_drawn` | `INTEGER` | Falli subiti |
| `fouls_committed` | `INTEGER` | Falli commessi |
| `yellow_cards` | `INTEGER` | Ammonizioni |
| `red_cards` | `INTEGER` | Espulsioni |
| `offsides` | `INTEGER` | Fuorigioco |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 7. match_team_stats
Statistiche di squadra aggregate per il match.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `fixture_id` | `INTEGER` | ID della partita |
| `team_id` | `INTEGER` | ID della squadra |
| `team_name` | `TEXT` | Nome della squadra |
| `stat_type` | `TEXT` | Tipo di statistica (es. "Ball Possession", "Expected Goals", "Shots insidebox") |
| `value_text` | `TEXT` | Valore in formato stringa |
| `value_numeric` | `FLOAT` | Valore in formato numerico |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 8. matches
Anagrafica principale delle partite.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `fixture_id` | `INTEGER` (PK) | ID unico della partita |
| `league_id` | `INTEGER` | ID della competizione |
| `season_year` | `INTEGER` | Anno della stagione |
| `fixture_date` | `TIMESTAMP` | Data e ora del match |
| `venue_name` | `TEXT` | Nome dello stadio |
| `venue_city` | `TEXT` | Città dello stadio |
| `status_short` | `TEXT` | Codice stato (FT, HT, TBD, PST) |
| `status_long` | `TEXT` | Descrizione stato match |
| `status_elapsed` | `INTEGER` | Minuti trascorsi |
| `home_team_id` | `INTEGER` | ID squadra casa |
| `home_team_name` | `TEXT` | Nome squadra casa |
| `away_team_id` | `INTEGER` | ID squadra trasferta |
| `away_team_name` | `TEXT` | Nome squadra trasferta |
| `goals_home` | `INTEGER` | Gol totali casa |
| `goals_away` | `INTEGER` | Gol totali trasferta |
| `halftime_home` | `INTEGER` | Gol nel primo tempo (casa) |
| `halftime_away` | `INTEGER` | Gol nel primo tempo (trasferta) |
| `fulltime_home` | `INTEGER` | Gol totali (casa) |
| `fulltime_away` | `INTEGER` | Gol totali (trasferta) |
| `extratime_home` | `INTEGER` | Gol nei supplementari (casa) |
| `extratime_away` | `INTEGER` | Gol nei supplementari (trasferta) |
| `penalty_home` | `INTEGER` | Gol ai rigori (casa) |
| `penalty_away` | `INTEGER` | Gol ai rigori (trasferta) |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 9. standings
Classifiche dei campionati.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `league_id` | `INTEGER` | ID della competizione |
| `season_year` | `INTEGER` | Anno della stagione |
| `standing_group` | `TEXT` | Nome del gruppo o girone |
| `rank` | `INTEGER` | Posizione in classifica |
| `team_id` | `INTEGER` | ID della squadra |
| `team_name` | `TEXT` | Nome della squadra |
| `played` | `INTEGER` | Partite giocate |
| `win` | `INTEGER` | Vittorie |
| `draw` | `INTEGER` | Pareggi |
| `lose` | `INTEGER` | Sconfitte |
| `goals_for` | `INTEGER` | Gol fatti |
| `goals_against` | `INTEGER` | Gol subiti |
| `goals_diff` | `INTEGER` | Differenza reti |
| `points` | `INTEGER` | Punti totali |
| `form` | `TEXT` | Forma recente (es. "WWDLW") |
| `description` | `TEXT` | Descrizione qualificazione/retrocessione |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 10. top_assists
Classifica dei migliori assist-man.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `league_id` | `INTEGER` | ID della competizione |
| `season_year` | `INTEGER` | Anno della stagione |
| `player_id` | `INTEGER` | ID unico del giocatore |
| `player_name` | `TEXT` | Nome del giocatore |
| `player_age` | `INTEGER` | Età del giocatore |
| `player_nationality` | `TEXT` | Nazionalità |
| `team_id` | `INTEGER` | ID squadra |
| `team_name` | `TEXT` | Nome squadra |
| `games_appearances` | `INTEGER` | Presenze |
| `games_lineups` | `INTEGER` | Partite da titolare |
| `games_minutes` | `INTEGER` | Minuti giocati |
| `goals_total` | `INTEGER` | Gol segnati |
| `goals_assists` | `INTEGER` | Assist totali |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 11. top_cards
Classifica dei giocatori con il maggior numero di sanzioni.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `league_id` | `INTEGER` | ID della competizione |
| `season_year` | `INTEGER` | Anno della stagione |
| `card_type` | `TEXT` | Tipo (yellow, red) |
| `player_id` | `INTEGER` | ID giocatore |
| `player_name` | `TEXT` | Nome giocatore |
| `team_id` | `INTEGER` | ID squadra |
| `team_name` | `TEXT` | Nome squadra |
| `games_appearances` | `INTEGER` | Presenze |
| `yellow_cards` | `INTEGER` | Totale gialli |
| `red_cards` | `INTEGER` | Totale rossi |
| `raw_json` | `JSONB` | Dati JSON originali |

---

## 12. top_scorers
Classifica dei capocannonieri.

| Colonna | Tipo di Dato | Descrizione |
| :--- | :--- | :--- |
| `league_id` | `INTEGER` | ID della competizione |
| `season_year` | `INTEGER` | Anno della stagione |
| `player_id` | `INTEGER` | ID giocatore |
| `player_name` | `TEXT` | Nome giocatore |
| `team_id` | `INTEGER` | ID squadra |
| `team_name` | `TEXT` | Nome squadra |
| `goals_total` | `INTEGER` | Gol totali |
| `penalties_scored` | `INTEGER` | Rigori segnati |
| `raw_json` | `JSONB` | Dati JSON originali |
