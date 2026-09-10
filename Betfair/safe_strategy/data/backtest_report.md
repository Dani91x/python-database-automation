# Backtest opportunita' in-play (registrazioni reali)

Generato: 2026-09-10T15:20:15+00:00 | eventi: 38 | stake: 5.00 EUR | commissione: 5% sul netto per mercato | durata: 114s
Fonte lambda: {'pre_ko': 21, 'default': 17} (default = lambda generici del bot, confidenza penalizzata)
Calibrazione: eventi 32, campioni 60911, tabelle applicate 36/36, Brier 0.0859 -> 0.0818 (CV: 0.0859 -> 0.0849), ECE 0.0143 -> 0.0090

## Sintesi per modalita'

| segmento | segnali | piazzabili | abbinati | abbinati % | puntato EUR | P&L EUR | ROI | hit | max DD EUR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw | 243 | 243 | 211 | 87% | 890 | -133.53 | -15.0% | 78% | 183.12 |
| calibrated | 252 | 252 | 224 | 89% | 895 | -1.69 | -0.2% | 82% | 95.42 |
| cv | 264 | 264 | 231 | 88% | 930 | -172.89 | -18.6% | 77% | 197.81 |

## Modalita' `raw` - per famiglia/lato

| segmento | segnali | piazzabili | abbinati | abbinati % | puntato EUR | P&L EUR | ROI | hit | max DD EUR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| btts/back | 5 | 5 | 2 | 40% | 10 | -2.34 | -23.4% | 50% | 5.00 |
| btts/lay | 3 | 3 | 3 | 100% | 15 | -10.00 | -66.7% | 67% | 19.50 |
| cs_any_other/back | 2 | 2 | 1 | 50% | 5 | +0.24 | +4.8% | 100% | 0.00 |
| cs_any_other/lay | 4 | 4 | 3 | 75% | 10 | +9.50 | +95.0% | 100% | 0.00 |
| cs_cell/back | 17 | 17 | 15 | 88% | 70 | -11.54 | -16.5% | 71% | 18.82 |
| cs_cell/lay | 9 | 9 | 9 | 100% | 40 | -5.50 | -13.8% | 75% | 20.00 |
| ht/back | 15 | 15 | 13 | 87% | 55 | -8.78 | -16.0% | 73% | 15.00 |
| ht/lay | 6 | 6 | 4 | 67% | 20 | -21.50 | -107.5% | 50% | 31.00 |
| hts_cell/back | 6 | 6 | 5 | 83% | 25 | +4.65 | +18.6% | 100% | 0.00 |
| hts_cell/lay | 6 | 6 | 4 | 67% | 15 | -10.50 | -70.0% | 67% | 20.00 |
| mo/back | 25 | 25 | 20 | 80% | 90 | -12.76 | -14.2% | 78% | 16.81 |
| mo/lay | 13 | 13 | 10 | 77% | 40 | -26.25 | -65.6% | 62% | 40.75 |
| ou_line/back | 95 | 95 | 87 | 92% | 345 | +0.49 | +0.1% | 86% | 26.39 |
| ou_line/lay | 37 | 37 | 35 | 95% | 150 | -39.25 | -26.2% | 70% | 72.75 |

Non abbinate (motivi): {'prezzo peggiorato/size 0 dopo il delay': 26, 'mercato SUSPENDED dopo il delay': 2, 'prezzo peggiorato/size 3 dopo il delay': 1, 'prezzo peggiorato/size 5 dopo il delay': 1, 'prezzo peggiorato/size 2 dopo il delay': 1, 'prezzo peggiorato/size 4 dopo il delay': 1}

## Modalita' `raw` - per evento

| evento | partita | finale | lambda | segnali | abbinati | P&L EUR | ROI |
|---|---|---|---|---:|---:|---:|---:|
| 35674515 | Qingdao Hainiu v Yunnan Yukun | 4-2 | pre_ko | 11 | 10 | -36.20 | -72.4% |
| 35759636 | Rigas Futbola Skola v BFC Daugavpils | 3-1 | default | 9 | 8 | +1.59 | +4.0% |
| 35760084 | Liepajas Metalurgs v Ogre United | 4-0 | pre_ko | 10 | 10 | +20.66 | +41.3% |
| 35764745 | Ivory Coast v Norway | 1-2 | pre_ko | 10 | 10 | +24.22 | +48.5% |
| 35765620 | Australia v Egypt | 1-1 | pre_ko | 10 | 9 | -5.56 | -12.3% |
| 35768297 | Portugal v Croatia | 2-1 | pre_ko | 14 | 12 | -34.10 | -56.8% |
| 35768365 | Spain v Austria | 3-0 | pre_ko | 11 | 9 | +18.43 | +41.0% |
| 35772591 | Nyiregyhaza v FC Zbrojovka Brno | 0-3 | default | 6 | 6 | -7.79 | -26.0% |
| 35774000 | MAS Taborsko v SKU Amstetten | 0-3 | pre_ko | 7 | 7 | +13.21 | +37.7% |
| 35777617 | Brazil v Norway | 1-2 | pre_ko | 17 | 15 | -64.67 | -86.2% |
| 35780184 | SK Super Nova v Ogre United | 1-2 | pre_ko | 11 | 10 | -28.09 | -56.2% |
| 35781607 | FK Suduva v TransINVEST Vilnius | 0-0 | pre_ko | 6 | 5 | +6.56 | +26.2% |
| 35784105 | Portugal v Spain | 0-1 | default | 5 | 3 | +0.00 | +0.0% |
| 35787218 | Argentina v Egypt | 3-2 | default | 15 | 13 | -53.00 | -81.5% |
| 35787327 | Switzerland v Colombia | 0-0 | pre_ko | 2 | 1 | +0.00 | +0.0% |
| 35788728 | Shandong Taishan v Yunnan Yukun | 4-3 | default | 6 | 6 | -11.14 | -37.1% |
| 35788742 | VPS v SJK | 0-0 | pre_ko | 4 | 2 | +0.00 | +0.0% |
| 35792347 | Cheonan City v Gimhae City | 0-1 | default | 3 | 3 | +1.19 | +7.9% |
| 35796477 | Shelbourne v Celtic | 1-1 | pre_ko | 3 | 3 | -4.66 | -31.1% |
| 35796504 | PAOK v AEK Larnaca | 3-2 | default | 2 | 2 | +0.62 | +6.2% |
| 35797538 | Zeleznicar Pancevo v CSKA 1948 Sofia | 0-1 | pre_ko | 8 | 8 | +15.72 | +39.3% |
| 35797769 | Spain v Belgium | 2-1 | pre_ko | 9 | 7 | +5.02 | +14.3% |
| 35804159 | SV Sandhausen v Kaiserslautern | 1-1 | default | 7 | 4 | +0.00 | +0.0% |
| 35804211 | FC Inter 2 v RoPS | 0-2 | default | 12 | 10 | -0.49 | -1.0% |
| 35804974 | Legia Warsaw v Trencin | 1-0 | default | 5 | 5 | +9.36 | +37.4% |
| 35812264 | Beijing Guoan v Liaoning Tieren FC | 1-1 | default | 9 | 6 | +13.58 | +45.3% |
| 35817305 | Elimai FC v Alashkert | 1-1 | pre_ko | 2 | 1 | +0.00 | +0.0% |
| 35817332 | FC Inter v Sarajevo | 0-1 | pre_ko | 2 | 2 | +0.00 | +0.0% |
| 35817978 | FC Astana v Dinamo Tirana | 1-0 | pre_ko | 3 | 2 | +0.00 | +0.0% |
| 35823368 | FC Copenhagen v Viborg | 2-1 | default | 6 | 6 | -5.00 | -100.0% |
| 35823369 | Nurnberg II v SC AUSTRIA LUSTENAU | 1-0 | default | 4 | 4 | +0.00 | +0.0% |
| 35823409 | Puskas Akademia v Basaksehir | 0-2 | default | 2 | 2 | +5.51 | +55.1% |
| 35826515 | Aarhus Fremad v Brabrand | 1-0 | default | 5 | 4 | -18.50 | -370.0% |
| 35828026 | HNK Gorica v FC Epicentr Dunaivtsi | 0-0 | pre_ko | 1 | 1 | +0.00 | +0.0% |
| 35833626 | Mainz v Kaiserslautern | 2-0 | default | 4 | 3 | +0.00 | +0.0% |
| 36006953 | Parma v US Cremonese | 0-2 | pre_ko | 2 | 2 | +0.00 | +0.0% |

## Modalita' `calibrated` - per famiglia/lato

| segmento | segnali | piazzabili | abbinati | abbinati % | puntato EUR | P&L EUR | ROI | hit | max DD EUR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| btts/back | 6 | 6 | 5 | 83% | 25 | -4.30 | -17.2% | 60% | 10.00 |
| btts/lay | 3 | 3 | 2 | 67% | 10 | +9.50 | +95.0% | 100% | 0.00 |
| cs_any_other/back | 2 | 2 | 1 | 50% | 5 | +0.24 | +4.8% | 100% | 0.00 |
| cs_any_other/lay | 5 | 5 | 4 | 80% | 15 | +14.25 | +95.0% | 100% | 0.00 |
| cs_cell/back | 12 | 12 | 10 | 83% | 45 | -6.79 | -15.1% | 67% | 13.60 |
| cs_cell/lay | 8 | 8 | 8 | 100% | 35 | -37.25 | -106.4% | 57% | 47.00 |
| ht/back | 6 | 6 | 6 | 100% | 15 | +3.28 | +21.9% | 100% | 0.00 |
| ht/lay | 4 | 4 | 3 | 75% | 15 | +14.25 | +95.0% | 100% | 0.00 |
| hts_cell/back | 3 | 3 | 3 | 100% | 15 | +2.42 | +16.1% | 100% | 0.00 |
| hts_cell/lay | 3 | 3 | 3 | 100% | 15 | -16.90 | -112.7% | 33% | 21.65 |
| mo/back | 24 | 24 | 20 | 83% | 90 | -9.34 | -10.4% | 78% | 15.76 |
| mo/lay | 10 | 10 | 6 | 60% | 25 | -22.60 | -90.4% | 40% | 27.60 |
| ou_line/back | 126 | 126 | 116 | 92% | 440 | +19.40 | +4.4% | 90% | 16.73 |
| ou_line/lay | 40 | 40 | 37 | 92% | 145 | +32.15 | +22.2% | 79% | 45.30 |

Non abbinate (motivi): {'prezzo peggiorato/size 0 dopo il delay': 23, 'mercato SUSPENDED dopo il delay': 3, 'prezzo peggiorato/size 3 dopo il delay': 1, 'prezzo peggiorato/size 4 dopo il delay': 1}

## Modalita' `calibrated` - per evento

| evento | partita | finale | lambda | segnali | abbinati | P&L EUR | ROI |
|---|---|---|---|---:|---:|---:|---:|
| 35674515 | Qingdao Hainiu v Yunnan Yukun | 4-2 | pre_ko | 13 | 12 | -49.02 | -81.7% |
| 35759636 | Rigas Futbola Skola v BFC Daugavpils | 3-1 | default | 8 | 7 | +2.29 | +6.5% |
| 35760084 | Liepajas Metalurgs v Ogre United | 4-0 | pre_ko | 11 | 11 | +20.85 | +37.9% |
| 35764745 | Ivory Coast v Norway | 1-2 | pre_ko | 11 | 10 | +22.13 | +44.3% |
| 35765620 | Australia v Egypt | 1-1 | pre_ko | 9 | 8 | -5.89 | -14.7% |
| 35768297 | Portugal v Croatia | 2-1 | pre_ko | 12 | 11 | -22.46 | -40.8% |
| 35768365 | Spain v Austria | 3-0 | pre_ko | 11 | 10 | +19.29 | +38.6% |
| 35772591 | Nyiregyhaza v FC Zbrojovka Brno | 0-3 | default | 5 | 5 | +12.30 | +49.2% |
| 35774000 | MAS Taborsko v SKU Amstetten | 0-3 | pre_ko | 8 | 8 | +14.87 | +37.2% |
| 35777617 | Brazil v Norway | 1-2 | pre_ko | 11 | 9 | +8.19 | +18.2% |
| 35780184 | SK Super Nova v Ogre United | 1-2 | pre_ko | 11 | 11 | -16.21 | -29.5% |
| 35781607 | FK Suduva v TransINVEST Vilnius | 0-0 | pre_ko | 9 | 8 | -16.57 | -41.4% |
| 35784105 | Portugal v Spain | 0-1 | default | 5 | 3 | +0.00 | +0.0% |
| 35787218 | Argentina v Egypt | 3-2 | default | 12 | 12 | -46.13 | -76.9% |
| 35787327 | Switzerland v Colombia | 0-0 | pre_ko | 4 | 3 | +0.00 | +0.0% |
| 35788728 | Shandong Taishan v Yunnan Yukun | 4-3 | default | 5 | 5 | +1.36 | +5.5% |
| 35788742 | VPS v SJK | 0-0 | pre_ko | 5 | 0 | +0.00 | +0.0% |
| 35792347 | Cheonan City v Gimhae City | 0-1 | default | 2 | 2 | +0.71 | +7.1% |
| 35796477 | Shelbourne v Celtic | 1-1 | pre_ko | 3 | 3 | -4.66 | -31.1% |
| 35796504 | PAOK v AEK Larnaca | 3-2 | default | 2 | 2 | +4.99 | +49.9% |
| 35797538 | Zeleznicar Pancevo v CSKA 1948 Sofia | 0-1 | pre_ko | 8 | 8 | +13.59 | +34.0% |
| 35797769 | Spain v Belgium | 2-1 | pre_ko | 10 | 9 | +11.45 | +25.4% |
| 35804159 | SV Sandhausen v Kaiserslautern | 1-1 | default | 5 | 3 | +0.00 | +0.0% |
| 35804211 | FC Inter 2 v RoPS | 0-2 | default | 10 | 10 | +4.78 | +9.6% |
| 35804974 | Legia Warsaw v Trencin | 1-0 | default | 5 | 5 | +8.36 | +33.4% |
| 35812264 | Beijing Guoan v Liaoning Tieren FC | 1-1 | default | 8 | 5 | +8.83 | +35.3% |
| 35817305 | Elimai FC v Alashkert | 1-1 | pre_ko | 4 | 2 | +1.00 | +19.9% |
| 35817332 | FC Inter v Sarajevo | 0-1 | pre_ko | 5 | 4 | +0.00 | +0.0% |
| 35817978 | FC Astana v Dinamo Tirana | 1-0 | pre_ko | 8 | 7 | +0.43 | +8.6% |
| 35823368 | FC Copenhagen v Viborg | 2-1 | default | 4 | 3 | +0.00 | +0.0% |
| 35823369 | Nurnberg II v SC AUSTRIA LUSTENAU | 1-0 | default | 5 | 5 | +0.00 | +0.0% |
| 35823409 | Puskas Akademia v Basaksehir | 0-2 | default | 4 | 4 | +6.55 | +32.8% |
| 35826515 | Aarhus Fremad v Brabrand | 1-0 | default | 5 | 5 | -3.15 | -63.0% |
| 35828026 | HNK Gorica v FC Epicentr Dunaivtsi | 0-0 | pre_ko | 2 | 2 | +0.00 | +0.0% |
| 35833626 | Mainz v Kaiserslautern | 2-0 | default | 6 | 6 | +0.00 | +0.0% |
| 36006953 | Parma v US Cremonese | 0-2 | pre_ko | 6 | 6 | +0.43 | +8.6% |

## Modalita' `cv` - per famiglia/lato

| segmento | segnali | piazzabili | abbinati | abbinati % | puntato EUR | P&L EUR | ROI | hit | max DD EUR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| btts/back | 6 | 6 | 4 | 67% | 20 | -0.49 | -2.4% | 75% | 5.00 |
| btts/lay | 4 | 4 | 3 | 75% | 15 | -10.00 | -66.7% | 67% | 19.50 |
| cs_any_other/back | 2 | 2 | 1 | 50% | 5 | +0.24 | +4.8% | 100% | 0.00 |
| cs_any_other/lay | 6 | 6 | 4 | 67% | 15 | -10.00 | -66.7% | 67% | 19.50 |
| cs_cell/back | 12 | 12 | 10 | 83% | 45 | -6.79 | -15.1% | 67% | 13.60 |
| cs_cell/lay | 9 | 9 | 9 | 100% | 40 | -52.75 | -131.9% | 50% | 62.50 |
| ht/back | 8 | 8 | 7 | 88% | 20 | -1.87 | -9.3% | 75% | 5.00 |
| ht/lay | 7 | 7 | 6 | 86% | 30 | -14.85 | -49.5% | 50% | 19.60 |
| hts_cell/back | 2 | 2 | 2 | 100% | 10 | +1.42 | +14.2% | 100% | 0.00 |
| hts_cell/lay | 4 | 4 | 4 | 100% | 20 | -35.90 | -179.5% | 25% | 40.65 |
| mo/back | 25 | 25 | 21 | 84% | 95 | -17.76 | -18.7% | 74% | 21.81 |
| mo/lay | 10 | 10 | 7 | 70% | 30 | -35.75 | -119.2% | 50% | 45.50 |
| ou_line/back | 129 | 129 | 117 | 91% | 445 | +9.55 | +2.1% | 89% | 22.20 |
| ou_line/lay | 40 | 40 | 36 | 90% | 140 | +2.05 | +1.5% | 75% | 49.00 |

Non abbinate (motivi): {'prezzo peggiorato/size 0 dopo il delay': 26, 'mercato SUSPENDED dopo il delay': 4, 'prezzo peggiorato/size 3 dopo il delay': 1, 'prezzo peggiorato/size 5 dopo il delay': 1, 'prezzo peggiorato/size 4 dopo il delay': 1}

## Modalita' `cv` - per evento

| evento | partita | finale | lambda | segnali | abbinati | P&L EUR | ROI |
|---|---|---|---|---:|---:|---:|---:|
| 35674515 | Qingdao Hainiu v Yunnan Yukun | 4-2 | pre_ko | 16 | 14 | -52.10 | -74.4% |
| 35759636 | Rigas Futbola Skola v BFC Daugavpils | 3-1 | default | 8 | 7 | +2.39 | +6.8% |
| 35760084 | Liepajas Metalurgs v Ogre United | 4-0 | pre_ko | 12 | 12 | +0.12 | +0.2% |
| 35764745 | Ivory Coast v Norway | 1-2 | pre_ko | 11 | 10 | +20.38 | +40.8% |
| 35765620 | Australia v Egypt | 1-1 | pre_ko | 10 | 9 | -10.89 | -24.2% |
| 35768297 | Portugal v Croatia | 2-1 | pre_ko | 12 | 11 | -28.35 | -51.5% |
| 35768365 | Spain v Austria | 3-0 | pre_ko | 10 | 9 | +12.16 | +27.0% |
| 35772591 | Nyiregyhaza v FC Zbrojovka Brno | 0-3 | default | 8 | 6 | -26.14 | -87.2% |
| 35774000 | MAS Taborsko v SKU Amstetten | 0-3 | pre_ko | 7 | 7 | +8.69 | +24.8% |
| 35777617 | Brazil v Norway | 1-2 | pre_ko | 12 | 8 | -31.90 | -79.8% |
| 35780184 | SK Super Nova v Ogre United | 1-2 | pre_ko | 11 | 11 | -16.59 | -30.2% |
| 35781607 | FK Suduva v TransINVEST Vilnius | 0-0 | pre_ko | 9 | 9 | -11.54 | -25.6% |
| 35784105 | Portugal v Spain | 0-1 | default | 5 | 3 | +0.00 | +0.0% |
| 35787218 | Argentina v Egypt | 3-2 | default | 14 | 13 | -61.11 | -94.0% |
| 35787327 | Switzerland v Colombia | 0-0 | pre_ko | 4 | 3 | +0.00 | +0.0% |
| 35788728 | Shandong Taishan v Yunnan Yukun | 4-3 | default | 5 | 5 | +1.36 | +5.5% |
| 35788742 | VPS v SJK | 0-0 | pre_ko | 5 | 0 | +0.00 | +0.0% |
| 35792347 | Cheonan City v Gimhae City | 0-1 | default | 2 | 2 | +0.71 | +7.1% |
| 35796477 | Shelbourne v Celtic | 1-1 | pre_ko | 3 | 3 | -4.66 | -31.1% |
| 35796504 | PAOK v AEK Larnaca | 3-2 | default | 1 | 1 | +0.24 | +4.8% |
| 35797538 | Zeleznicar Pancevo v CSKA 1948 Sofia | 0-1 | pre_ko | 8 | 8 | +13.59 | +34.0% |
| 35797769 | Spain v Belgium | 2-1 | pre_ko | 10 | 8 | +10.83 | +27.1% |
| 35804159 | SV Sandhausen v Kaiserslautern | 1-1 | default | 5 | 3 | +0.00 | +0.0% |
| 35804211 | FC Inter 2 v RoPS | 0-2 | default | 11 | 11 | -5.97 | -10.9% |
| 35804974 | Legia Warsaw v Trencin | 1-0 | default | 6 | 6 | -7.14 | -23.8% |
| 35812264 | Beijing Guoan v Liaoning Tieren FC | 1-1 | default | 8 | 6 | +13.58 | +45.3% |
| 35817305 | Elimai FC v Alashkert | 1-1 | pre_ko | 4 | 2 | +1.00 | +19.9% |
| 35817332 | FC Inter v Sarajevo | 0-1 | pre_ko | 5 | 4 | +0.00 | +0.0% |
| 35817978 | FC Astana v Dinamo Tirana | 1-0 | pre_ko | 8 | 7 | +0.43 | +8.6% |
| 35823368 | FC Copenhagen v Viborg | 2-1 | default | 5 | 4 | -5.00 | -100.0% |
| 35823369 | Nurnberg II v SC AUSTRIA LUSTENAU | 1-0 | default | 5 | 5 | +0.00 | +0.0% |
| 35823409 | Puskas Akademia v Basaksehir | 0-2 | default | 4 | 4 | +6.60 | +33.0% |
| 35826515 | Aarhus Fremad v Brabrand | 1-0 | default | 6 | 6 | -4.00 | -40.0% |
| 35828026 | HNK Gorica v FC Epicentr Dunaivtsi | 0-0 | pre_ko | 2 | 2 | +0.00 | +0.0% |
| 35833626 | Mainz v Kaiserslautern | 2-0 | default | 6 | 6 | +0.00 | +0.0% |
| 36006953 | Parma v US Cremonese | 0-2 | pre_ko | 6 | 6 | +0.43 | +8.6% |

## Avvertenze

- `calibrated` usa tabelle stimate ANCHE su questi eventi (in-sample): guardare `cv` (leave-one-event-out).
- Una scommessa per (mercato, selezione, lato) per evento; nessun cash-out, nessuna uscita: si regola al risultato.
- Il book registrato e' il best 3 livelli del feed: l'abbinamento dopo il delay e' una stima, non un fill certo.
- Atlante Hazard non caricato (controincrocio assente, come nel bot senza atlante).
- Gli eventi senza quote 1X2 pre-KO usano i lambda generici del bot (fonte `default`).
- Esiti correlati dentro la stessa partita: n eventi e' la vera numerosita', non n segnali.
