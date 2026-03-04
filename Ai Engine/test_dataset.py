import sys, os
import pandas as pd
from ai_engine.db_client import fetch_seasons_for_league
from ai_engine.training_dataset import build_training_dataset

league_id = 266
seasons = fetch_seasons_for_league(league_id)
print(f"Seasons found for league {league_id}: {seasons}")
seasons_to_use = seasons[-3:] if len(seasons) > 3 else seasons
league_seasons = [(league_id, s) for s in seasons_to_use]

train_df = build_training_dataset(league_seasons)
print(f"Shape of train_df: {train_df.shape}")
if not train_df.empty:
    print("Columns:", list(train_df.columns)[:10])
    if 'target_1x2' in train_df.columns:
        print(f"Rows of target_1x2 nulls: {train_df['target_1x2'].isna().sum()}")
        print("Value counts for target_1x2:\n", train_df['target_1x2'].value_counts(dropna=False))
else:
    print("Dataframe is totally empty.")
