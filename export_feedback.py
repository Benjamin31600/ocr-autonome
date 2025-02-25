import sqlite3
import pandas as pd

conn = sqlite3.connect("feedback.db")
df = pd.read_sql_query("SELECT ocr_text, corrected_text FROM feedback", conn)
df.to_csv("feedback_data.csv", index=False)
conn.close()
print("Données exportées dans feedback_data.csv")
