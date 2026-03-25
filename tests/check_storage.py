# tests/check_storage.py
# Ce script inspecte les 3 storages pour voir ce qui a été sauvegardé

import sqlite3
import json
import os

print("\n" + "="*55)
print("  SQLITE — leads.db")
print("="*55)

db_path = "data/leads.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Tous les leads
    leads = conn.execute("SELECT * FROM leads ORDER BY created_at").fetchall()
    print(f"Total leads : {len(leads)}")
    print()
    for l in leads:
        print(f"  [{l['campaign'][:8]}] {l['name']} @ {l['company']}")
        print(f"    status={l['status']} | score={l['score']} | {l['created_at'][:10]}")

    # Toutes les campagnes
    print("\n" + "-"*55)
    print("  CAMPAGNES")
    print("-"*55)
    campaigns = conn.execute("SELECT * FROM campaigns ORDER BY created_at").fetchall()
    for c in campaigns:
        print(f"  ID: {c['id']} | leads: {c['leads_count']}")
        print(f"  Prompt: {c['prompt'][:70]}")
        print()

    conn.close()
else:
    print("  Fichier leads.db introuvable")

print("="*55)
print("  JSON — leads_raw.json")
print("="*55)

json_path = "data/leads_raw.json"
if os.path.exists(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"Total entrées JSON : {len(data)}")
    campaigns_seen = {}
    for lead in data:
        cid = lead.get("campaign_id", "unknown")
        if cid not in campaigns_seen:
            campaigns_seen[cid] = []
        campaigns_seen[cid].append(lead.get("name", "unknown"))
    for cid, names in campaigns_seen.items():
        print(f"\n  Campagne {cid} : {len(names)} leads")
        for n in names:
            print(f"    - {n}")
else:
    print("  Fichier leads_raw.json introuvable")

print("\n" + "="*55)
print("  CHROMADB")
print("="*55)

try:
    import chromadb
    client = chromadb.PersistentClient(path="data/chroma")
    collection = client.get_or_create_collection("leads")
    count = collection.count()
    print(f"Total vecteurs ChromaDB : {count}")
    if count > 0:
        results = collection.get()
        for i, doc in enumerate(results["documents"]):
            meta = results["metadatas"][i]
            print(f"  - {meta.get('name','?')} @ {meta.get('company','?')}")
except Exception as e:
    print(f"  ChromaDB error: {e}")