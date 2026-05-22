from memory.storage import get_conn, get_sender_config
from agents.sender_node import send_email

def test_sender_config():
    """Test 1: Vérifier sender config"""
    print("\n" + "="*70)
    print("TEST 1: Sender Configuration")
    print("="*70)
    
    sender = get_sender_config()
    
    if not sender:
        print("❌ ERREUR: Pas de sender config")
        print("\nSOLUTION:")
        print("python")
        print(">>> from memory.storage import save_sender_config")
        print(">>> save_sender_config(name='Amine', email='aminebrahmity12@gmail.com', is_default=True)")
        return False
    
    print("✅ Sender config trouvée:")
    print(f"   Name: {sender.get('name')}")
    print(f"   Email: {sender.get('email')}")
    print(f"   SMTP User: {sender.get('smtp_user') or 'from .env'}")
    return True


def test_smtp_send():
    """Test 2: Envoyer un email de test"""
    print("\n" + "="*70)
    print("TEST 2: SMTP Send")
    print("="*70)
    
    sender = get_sender_config()
    if not sender:
        print("❌ Skipped (pas de sender config)")
        return False
    
    print("Envoi email de test...")
    
    result = send_email(
        sender,
        "aminebrahmity12@gmail.com",
        "Test Diagnostic",
        "Test body from diagnostic script",
        None
    )
    
    if result.get("success"):
        print(f"✅ Email envoyé avec succès")
        print(f"   Message ID: {result.get('message_id')}")
        return True
    else:
        print(f"❌ ERREUR SMTP: {result.get('error')}")
        return False


def test_email_sequences_table():
    """Test 3: Vérifier la table email_sequences"""
    print("\n" + "="*70)
    print("TEST 3: Table email_sequences")
    print("="*70)
    
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            
            # Vérifier si la table existe
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'email_sequences'
                )
            """)
            
            exists = cursor.fetchone()[0]
            
            if not exists:
                print("❌ Table email_sequences n'existe pas")
                print("\nSOLUTION:")
                print("CREATE TABLE email_sequences (")
                print("    id SERIAL PRIMARY KEY,")
                print("    lead_id VARCHAR(255) NOT NULL,")
                print("    campaign VARCHAR(255),")
                print("    variant VARCHAR(10),")
                print("    status VARCHAR(50),")
                print("    step INTEGER,")
                print("    subject TEXT,")
                print("    body TEXT,")
                print("    cc TEXT,")
                print("    scheduled_at TIMESTAMP,")
                print("    sent_at TIMESTAMP,")
                print("    created_at TIMESTAMP DEFAULT NOW()")
                print(");")
                return False
            
            print("✅ Table email_sequences existe")
            
            # Vérifier les colonnes
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'email_sequences'
                ORDER BY ordinal_position
            """)
            
            columns = cursor.fetchall()
            print(f"\n   Colonnes ({len(columns)}):")
            for col_name, col_type in columns:
                print(f"   - {col_name}: {col_type}")
            
            # Compter les lignes
            cursor.execute("SELECT COUNT(*) FROM email_sequences")
            count = cursor.fetchone()[0]
            print(f"\n   Nombre de séquences: {count}")
            
            return True
            
    except Exception as e:
        print(f"❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sequence_insert():
    """Test 4: Insérer une séquence de test"""
    print("\n" + "="*70)
    print("TEST 4: Insertion dans email_sequences")
    print("="*70)
    
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            
            # Trouver un lead existant
            cursor.execute("SELECT id, campaign FROM leads LIMIT 1")
            row = cursor.fetchone()
            
            if not row:
                print("❌ Pas de leads dans la DB")
                return False
            
            lead_id, campaign = row
            print(f"Test avec lead: {lead_id}")
            
            # Insérer une séquence de test
            cursor.execute("""
                INSERT INTO email_sequences 
                (lead_id, campaign, variant, status, step, subject, body, cc, scheduled_at, sent_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                lead_id,
                campaign,
                "TEST",
                "sent",
                0,
                "Test Subject",
                "Test Body",
                None
            ))
            
            sequence_id = cursor.fetchone()[0]
            conn.commit()
            
            print(f"✅ Séquence créée avec succès: ID={sequence_id}")
            
            # Supprimer la séquence de test
            cursor.execute("DELETE FROM email_sequences WHERE id = %s", (sequence_id,))
            conn.commit()
            print("   (séquence de test supprimée)")
            
            return True
            
    except Exception as e:
        print(f"❌ ERREUR lors de l'insertion: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_lead_update():
    """Test 5: Mettre à jour un lead"""
    print("\n" + "="*70)
    print("TEST 5: Mise à jour du lead")
    print("="*70)
    
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            
            # Trouver un lead
            cursor.execute("SELECT id, status FROM leads LIMIT 1")
            row = cursor.fetchone()
            
            if not row:
                print("❌ Pas de leads")
                return False
            
            lead_id, old_status = row
            print(f"Lead: {lead_id}, Status: {old_status}")
            
            # Mettre à jour
            cursor.execute("""
                UPDATE leads
                SET status = 'sent',
                    last_sent_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (lead_id,))
            
            conn.commit()
            
            print(f"✅ Lead mis à jour avec succès")
            
            # Remettre l'ancien statut
            cursor.execute("UPDATE leads SET status = %s WHERE id = %s", (old_status, lead_id))
            conn.commit()
            print(f"   (statut restauré à '{old_status}')")
            
            return True
            
    except Exception as e:
        print(f"❌ ERREUR lors de la mise à jour: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*70)
    print(" DIAGNOSTIC ERREUR 500 - ENVOI EMAIL")
    print("="*70)
    print("\nCe script va tester chaque étape de l'envoi d'email")
    print("pour identifier où se produit l'erreur 500.\n")
    
    results = {}
    
    results["sender_config"] = test_sender_config()
    results["smtp_send"] = test_smtp_send()
    results["email_sequences_table"] = test_email_sequences_table()
    results["sequence_insert"] = test_sequence_insert()
    results["lead_update"] = test_lead_update()
    
    # Résumé
    print("\n" + "="*70)
    print(" RÉSUMÉ")
    print("="*70)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_pass = all(results.values())
    
    print("\n" + "="*70)
    
    if all_pass:
        print("✅ TOUS LES TESTS PASSENT")
        print("\nL'erreur 500 vient probablement de:")
        print("1. Un problème de timeout")
        print("2. Une erreur non catchée dans la route")
        print("3. Un problème de sérialisation JSON")
        print("\nUtiliser la route simplifiée dans simple_send_route.py")
    else:
        print("❌ DES TESTS ONT ÉCHOUÉ")
        print("\nCorrigez les erreurs ci-dessus avant de continuer")
    
    print("="*70 + "\n")


if __name__ == "__main__":
    main()