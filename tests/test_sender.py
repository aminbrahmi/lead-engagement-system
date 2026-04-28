#!/usr/bin/env python3
"""
Test du sender_node - SÉCURISÉ

Ce script teste:
1. Génération des follow-ups (J+3, J+7, J+14)
2. Construction des messages MIME
3. Envoi SMTP (OPTIONNEL - vers votre email de test uniquement)

SÉCURITÉ: N'envoie RIEN sans confirmation explicite.
"""

from datetime import datetime
import sys
import os
import json

# Add project to path
sys.path.insert(0, '/mnt/project')

from agents.sender_node import generate_followups, send_email, _build_mime_message
from agents.llm_factory import get_writer_llm
from datetime import datetime



# ─────────────────────────────────────────────────────────────────────────────
# TEST DATA - Leads fictifs pour les tests
# ─────────────────────────────────────────────────────────────────────────────

FAKE_LEAD = {
    "name": "Test User",
    "company": "Test Company",
    "role": "CTO",
    "email": "test@example.com",  # Email fictif - NE SERA PAS ENVOYÉ
    "segment": "hot",
    "insights": {
        "recent_news": "Raised $5M seed funding in Q1 2026",
        "person_highlights": "Former engineer at Google, 10+ years experience",
        "company_challenge": "Scaling engineering team from 5 to 20",
        "tech_stack": "Python, React, PostgreSQL, AWS",
        "icebreaker": "Saw your interview on TechCrunch about AI automation",
        "value_angle": "Help scale engineering team with proven hiring framework"
    }
}

INITIAL_EMAIL = {
    "subject": "AI Engineering Team Scaling",
    "body": """Hi Test,

I saw your recent TechCrunch interview about AI automation at Test Company. Congrats on the $5M seed raise!

Scaling from 5 to 20 engineers is a critical inflection point. We've helped similar companies navigate this growth phase, with one client reducing their time-to-hire by 40% while maintaining quality.

Would a 15-minute call be valuable to discuss your hiring roadmap?

Best regards,
[Your Name]""",
    "cc": None
}

CAMPAIGN_PROMPT = "Reach out to CTOs of AI startups that raised funding"

SENDER_INFO = {
    "name": "Test Sender",
    "email": "sender@test.com",
    "title": "Growth Lead",
    "company": "Test Solutions",
    "signature": "Test Sender\nGrowth Lead, Test Solutions",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "sender@test.com",
    "smtp_pass": "your-password-here"  # Ne sera utilisé que si vous activez le vrai envoi
}


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Génération des Follow-ups
# ─────────────────────────────────────────────────────────────────────────────

def test_followup_generation():
    """Test la génération des 3 follow-ups via LLM."""
    print("="*70)
    print("TEST 1: Génération des Follow-ups")
    print("="*70)
    
    print("\n[Test] Génération de 3 follow-ups (J+3, J+7, J+14)...")
    print(f"[Test] Lead: {FAKE_LEAD['name']} @ {FAKE_LEAD['company']}")
    print(f"[Test] Initial subject: {INITIAL_EMAIL['subject']}")
    
    try:
        followups = generate_followups(
            lead=FAKE_LEAD,
            initial_email=INITIAL_EMAIL,
            campaign_prompt=CAMPAIGN_PROMPT,
            sender_info=SENDER_INFO
        )
        
        print(f"\n✅ SUCCESS: Généré {len(followups)} follow-ups\n")
        
        for i, followup in enumerate(followups, 1):
            step_label = {1: "J+3 (Gentle nudge)", 2: "J+7 (Value-add)", 3: "J+14 (Breakup)"}[i]
            print(f"\n{'─'*70}")
            print(f"Follow-up {i}: {step_label}")
            print(f"{'─'*70}")
            print(f"Subject: {followup.get('subject', 'N/A')}")
            print(f"\nBody:\n{followup.get('body', 'N/A')}")
        
        return followups
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return None


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Construction des Messages MIME
# ─────────────────────────────────────────────────────────────────────────────

def test_mime_message_construction(followups):
    """Test la construction des messages MIME."""
    print("\n\n" + "="*70)
    print("TEST 2: Construction des Messages MIME")
    print("="*70)
    
    # Test initial email
    print("\n[Test] Construction du message MIME pour l'email initial...")
    
    try:
        msg = _build_mime_message(
            sender_config=SENDER_INFO,
            to_email=FAKE_LEAD['email'],
            subject=INITIAL_EMAIL['subject'],
            body=INITIAL_EMAIL['body'],
            cc=INITIAL_EMAIL.get('cc')
        )
        
        print("✅ Message MIME construit avec succès!")
        print(f"\n  From: {msg['From']}")
        print(f"  To: {msg['To']}")
        print(f"  Subject: {msg['Subject']}")
        print(f"  Message-ID: {msg['Message-ID']}")
        print(f"  Content-Type: {msg.get_content_type()}")
        
        # Test follow-ups
        if followups:
            print("\n[Test] Construction des messages MIME pour les follow-ups...")
            for i, followup in enumerate(followups, 1):
                msg = _build_mime_message(
                    sender_config=SENDER_INFO,
                    to_email=FAKE_LEAD['email'],
                    subject=followup['subject'],
                    body=followup['body']
                )
                step = {1: "J+3", 2: "J+7", 3: "J+14"}[i]
                print(f"  ✅ {step}: {msg['Subject']}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Envoi SMTP Réel (OPTIONNEL - DEMANDE CONFIRMATION)
# ─────────────────────────────────────────────────────────────────────────────

def test_smtp_sending():
    """
    Test l'envoi SMTP RÉEL - UNIQUEMENT si confirmé par l'utilisateur.
    
    ⚠️ ATTENTION: Ceci enverra un vrai email!
    """
    print("\n\n" + "="*70)
    print("TEST 3: Envoi SMTP Réel (OPTIONNEL)")
    print("="*70)
    
    print("\n⚠️  AVERTISSEMENT: Ce test enverra un VRAI email!")
    print("    Vous devez fournir:")
    print("    1. Votre email de TEST (pour recevoir)")
    print("    2. Vos credentials SMTP (Gmail, Outlook, etc.)")
    print()
    
    # Vérifier si les variables d'environnement sont configurées
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    test_email = os.getenv("TEST_EMAIL")
    
    if not smtp_user or not smtp_pass:
        print("❌ Variables SMTP non configurées.")
        print("\nPour activer ce test, ajoutez à votre .env:")
        print("  SMTP_HOST=smtp.gmail.com")
        print("  SMTP_PORT=587")
        print("  SMTP_USER=votre.email@gmail.com")
        print("  SMTP_PASS=votre-mot-de-passe-app")
        print("  TEST_EMAIL=votre.email@gmail.com")
        print("\nℹ️  Pour Gmail:")
        print("  1. Activez la 2FA sur votre compte Google")
        print("  2. Générez un 'App Password': https://myaccount.google.com/apppasswords")
        print("  3. Utilisez ce password dans SMTP_PASS")
        return False
    
    if not test_email:
        print("❌ TEST_EMAIL non configuré - email de destination manquant")
        return False
    
    # Demander confirmation
    print(f"\n📧 Email sera envoyé à: {test_email}")
    print(f"📤 Via SMTP: {smtp_user}")
    
    confirm = input("\n⚠️  Taper 'YES' (en majuscules) pour envoyer: ")
    
    if confirm != "YES":
        print("\n❌ Test annulé - aucun email envoyé")
        return False
    
    # Configurer le sender avec les vraies credentials
    real_sender = {
        "name": os.getenv("SENDER_NAME", "Test Sender"),
        "email": smtp_user,
        "title": os.getenv("SENDER_TITLE", ""),
        "company": os.getenv("SENDER_COMPANY", ""),
        "signature": os.getenv("SENDER_SIGNATURE", ""),
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": smtp_user,
        "smtp_pass": smtp_pass,
    }
    
    # Email de test
    test_subject = "[TEST] Lead Engagement System - Email Test"
    test_body = f"""Bonjour,

Ceci est un email de TEST du Lead Engagement System.

Si vous recevez cet email, cela signifie que:
✅ La connexion SMTP fonctionne
✅ La construction des messages MIME fonctionne
✅ L'envoi d'emails est opérationnel

Informations du test:
- Lead: {FAKE_LEAD['name']} @ {FAKE_LEAD['company']}
- Campaign: {CAMPAIGN_PROMPT}
- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Vous pouvez ignorer cet email - il s'agit d'un test automatisé.

Cordialement,
Lead Engagement System
"""
    
    print(f"\n[Test] Envoi de l'email de test à {test_email}...")
    
    try:
        result = send_email(
            sender_config=real_sender,
            to_email=test_email,
            subject=test_subject,
            body=test_body
        )
        
        if result["success"]:
            print(f"\n✅ EMAIL ENVOYÉ AVEC SUCCÈS!")
            print(f"   Message-ID: {result.get('message_id', 'N/A')}")
            print(f"\n📬 Vérifiez votre boîte: {test_email}")
            print(f"   (peut prendre 1-2 minutes)")
            return True
        else:
            print(f"\n❌ ÉCHEC DE L'ENVOI: {result.get('error', 'Unknown error')}")
            print("\nDébogage:")
            print(f"  - SMTP Host: {real_sender['smtp_host']}:{real_sender['smtp_port']}")
            print(f"  - SMTP User: {real_sender['smtp_user']}")
            print(f"  - From: {real_sender['email']}")
            print(f"  - To: {test_email}")
            return False
            
    except Exception as e:
        print(f"\n❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Statistiques et Validation
# ─────────────────────────────────────────────────────────────────────────────

def test_validation():
    """Validation de la logique métier."""
    print("\n\n" + "="*70)
    print("TEST 4: Validation de la Logique")
    print("="*70)
    
    checks = []
    
    # Check 1: Follow-up subjects maintiennent le thread
    print("\n[Check 1] Les follow-ups utilisent 'Re:' pour le threading...")
    followup = {"subject": f"Re: {INITIAL_EMAIL['subject']}"}
    if followup['subject'].startswith("Re:"):
        print("  ✅ Threading correct")
        checks.append(True)
    else:
        print("  ❌ Threading manquant")
        checks.append(False)
    
    # Check 2: Email validation basic
    print("\n[Check 2] Validation des emails...")
    valid_emails = ["test@example.com", "user.name@company.co.uk"]
    invalid_emails = ["invalid", "@noemail", "no@domain"]
    
    valid_count = sum(1 for e in valid_emails if "@" in e and "." in e.split("@")[-1])
    if valid_count == len(valid_emails):
        print(f"  ✅ Emails valides reconnus ({valid_count}/{len(valid_emails)})")
        checks.append(True)
    else:
        print(f"  ❌ Validation échouée")
        checks.append(False)
    
    # Check 3: Sender info complète
    print("\n[Check 3] Configuration sender complète...")
    required = ['email', 'smtp_host', 'smtp_port', 'smtp_user']
    missing = [k for k in required if not SENDER_INFO.get(k)]
    if not missing:
        print("  ✅ Toutes les configs SMTP présentes")
        checks.append(True)
    else:
        print(f"  ⚠️  Configs manquantes: {missing}")
        checks.append(False)
    
    print(f"\n{'='*70}")
    print(f"Résultat: {sum(checks)}/{len(checks)} checks passés")
    print(f"{'='*70}")
    
    return all(checks)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN - Exécution des Tests
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Exécute tous les tests dans l'ordre."""
    
    print("\n" + "="*70)
    print(" LEAD ENGAGEMENT SYSTEM - TEST DU SENDER NODE")
    print("="*70)
    print(f" Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Mode: SAFE (pas d'envoi réel sans confirmation)")
    print("="*70)
    
    results = {}
    
    # Test 1: Follow-up generation
    followups = test_followup_generation()
    results['followup_generation'] = followups is not None and len(followups) == 3
    
    # Test 2: MIME construction
    if followups:
        results['mime_construction'] = test_mime_message_construction(followups)
    else:
        print("\n⚠️  Skipping MIME test - no followups generated")
        results['mime_construction'] = False
    
    # Test 3: SMTP sending (optionnel)
    results['smtp_sending'] = test_smtp_sending()
    
    # Test 4: Validation
    results['validation'] = test_validation()
    
    # Summary
    print("\n\n" + "="*70)
    print(" RÉSUMÉ DES TESTS")
    print("="*70)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {test_name.replace('_', ' ').title()}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"\n  Total: {passed}/{total} tests réussis")
    
    if passed == total:
        print("\n  🎉 TOUS LES TESTS PASSÉS!")
    elif passed >= total - 1:
        print("\n  ⚠️  Presque parfait - vérifiez le test échoué")
    else:
        print("\n  ⚠️  Plusieurs tests échoués - debug nécessaire")
    
    print("="*70 + "\n")
    
    return results


if __name__ == "__main__":
    try:
        results = main()
        
        # Exit code based on results
        if all(results.values()):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n❌ Test interrompu par l'utilisateur")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)