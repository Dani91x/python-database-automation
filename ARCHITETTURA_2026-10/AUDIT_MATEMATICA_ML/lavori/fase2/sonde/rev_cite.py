# Sonda di revisione: stampa le righe citate (sola lettura).
import sys
R = sys.argv[1]
C = [
 ("Betfair/stream/trading/dutching.py",184,186),("Betfair/stream/trading/dutching.py",224,224),("Betfair/stream/trading/dutching.py",239,244),
 ("Ai Engine/ai_engine/seriea_model_export.py",401,401),("Ai Engine/ai_engine/seriea_model_export.py",234,236),("Ai Engine/ai_engine/seriea_model_export.py",262,262),("Ai Engine/ai_engine/seriea_model_export.py",362,366),("Ai Engine/ai_engine/seriea_model_export.py",50,50),
 ("Ai Engine/ai_engine/confidence_gate.py",170,172),("Ai Engine/ai_engine/confidence_gate.py",215,215),
 ("valida_motore_poisson.py",28,28),("valida_motore_poisson.py",96,96),
 ("Betfair/safe_strategy/engine.py",1567,1567),("Betfair/safe_strategy/bot_service.py",5295,5296),("Betfair/safe_strategy/bot_service.py",193,193),
 ("Ai Engine/ai_engine/feature_pipeline.py",35,36),("Ai Engine/ai_engine/feature_pipeline.py",82,82),
 ("Ai Engine/ai_engine/ensemble_trainer.py",866,872),("Ai Engine/ai_engine/predict_fixture.py",870,872),("Ai Engine/ai_engine/predict_fixture.py",909,909),
 ("Betfair/stream/db.py",262,264),("Betfair/stream/db.py",285,285),("Betfair/mike/dossier.py",81,83),("Betfair/mike/dossier.py",102,102),("Betfair/mike/dossier.py",107,107),
 ("Betfair/stream/engine/live_engine_pro.py",596,607),("Betfair/safe_strategy/opportunity.py",1007,1007),("Betfair/stream/engine/live_engine_pro.py",58,72),
 ("Betfair/stream/scalper/theta_bot.py",546,551),("Betfair/stream/scalper/bias_resolver.py",79,92),
 ("Betfair/mike/COSTITUZIONE_MIKE.md",157,158),("Betfair/stream/config_stream.py",325,325),("poisson_calibrator.py",86,92),
 ("Betfair/money_management.py",1333,1333),("Betfair/money_management.py",2608,2608),("Betfair/omega/omega_advisor.py",309,309),
 ("Betfair/stream/live_order_build.py",99,99),("Betfair/stream/live_order_build.py",875,886),("tactical_engine/serving.py",46,48),
]
for p,a,b in C:
    L = open(R+"/"+p,encoding="utf-8",errors="replace").read().split("\n")
    print("=====",p,a,b,"(tot",len(L),")")
    for i in range(a,b+1):
        if i-1 < len(L): print(i, L[i-1][:170].encode("ascii","replace").decode())
