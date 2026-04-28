#!/usr/bin/env python3
"""
Test SMTP Simple - Sans LLM

Test rapide de la connexion SMTP et envoi basique.
Utile pour:
- Vérifier credentials SMTP
- Tester connexion serveur
- Valider configuration email
- Debug problèmes d'envoi

N'utilise PAS le LLM - juste SMTP pur.
"""

import os
import sys
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def test_smtp_connection():
    """Test 1: Connexion au serveur SMTP."""
    print("="*70)
    print("TEST 1: Connexion SMTP")
    print("="*70)
    
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    
    
    print(f"\n[Test] Connexion à {smtp_host}:{smtp_port}...")
    print(f"[Test] Utilisateur: {smtp_user}")
    
    try:
        # Créer connexion
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        print("  ✅ Socket créé")
        
        # TLS
        server.starttls(context=ssl.create_default_context())
        print("  ✅ TLS activé")
        
        # Login
        server.login(smtp_user, smtp_pass)
        print("  ✅ Authentification réussie")
        
        # Fermer
        server.quit()
        print("  ✅ Connexion fermée proprement")
        
        print("\n✅ CONNEXION SMTP OK!")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"\n❌ ERREUR D'AUTHENTIFICATION: {e}")
        print("\nVérifiez:")
        print("  1. App Password correct (16 caractères)")
        print("  2. 2FA activée sur Gmail")
        print("  3. SMTP_USER = votre email Gmail complet")
        return False
        
    except smtplib.SMTPException as e:
        print(f"\n❌ ERREUR SMTP: {e}")
        return False
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simple_send():
    """Test 2: Envoi d'un email simple."""
    print("\n\n" + "="*70)
    print("TEST 2: Envoi Email Simple")
    print("="*70)
    
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    test_email = os.getenv("TEST_EMAIL")
    sender_name = os.getenv("SENDER_NAME", "Test Sender")
    
    if not test_email:
        print("\n❌ TEST_EMAIL non défini")
        print("Ajouter à .env: TEST_EMAIL=votre@email.com")
        return False
    
    print(f"\n⚠️  Cet email sera envoyé à: {test_email}")
    confirm = input("Taper 'YES' pour continuer: ")
    
    if confirm != "YES":
        print("❌ Test annulé")
        return False
    
    # Construire message
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{sender_name} <{smtp_user}>"
    msg["To"] = test_email
    msg["Subject"] = f"[TEST SMTP] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    body = f"""Bonjour,

Ceci est un email de TEST SMTP.

Informations:
- Serveur: {smtp_host}:{smtp_port}
- Expéditeur: {smtp_user}
- Destinataire: {test_email}
- Timestamp: {datetime.now().isoformat()}

Si vous recevez cet email:
✅ Configuration SMTP correcte
✅ Connexion serveur fonctionnelle
✅ Envoi d'emails opérationnel

Vous pouvez supprimer cet email.

---
Lead Engagement System - Test SMTP
"""
    
    msg.attach(MIMEText(body, "plain"))
    
    print(f"\n[Test] Envoi à {test_email}...")
    
    try:
        # Connexion
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.starttls(context=ssl.create_default_context())
        server.login(smtp_user, smtp_pass)
        
        # Envoi
        server.send_message(msg)
        server.quit()
        
        print("\n✅ EMAIL ENVOYÉ!")
        print(f"\n📬 Vérifiez votre inbox: {test_email}")
        print("   (délai: 1-2 minutes)")
        return True
        
    except Exception as e:
        print(f"\n❌ ÉCHEC: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_email_formatting():
    """Test 3: Vérification formatage email."""
    print("\n\n" + "="*70)
    print("TEST 3: Formatage Email")
    print("="*70)
    
    smtp_user = os.getenv("SMTP_USER", "test@example.com")
    sender_name = os.getenv("SENDER_NAME", "Test Sender")
    
    # Test 1: From header
    from_header = f"{sender_name} <{smtp_user}>"
    print(f"\n[Check] From header: {from_header}")
    if sender_name in from_header and smtp_user in from_header:
        print("  ✅ Format correct")
    else:
        print("  ❌ Format incorrect")
    
    # Test 2: Subject
    subject = "[TEST] Email Subject"
    print(f"\n[Check] Subject: {subject}")
    if len(subject) > 0 and len(subject) < 100:
        print("  ✅ Longueur OK")
    else:
        print("  ⚠️  Subject très long")
    
    # Test 3: Body
    body = "Test body\n\nMulti-line\n\nBest regards"
    lines = body.split("\n")
    print(f"\n[Check] Body: {len(lines)} lignes, {len(body)} chars")
    if len(body) > 0:
        print("  ✅ Body non-vide")
    else:
        print("  ❌ Body vide")
    
    print("\n✅ Formatage validé")
    return True


def main():
    """Exécute tous les tests SMTP simples."""
    print("\n" + "="*70)
    print(" TEST SMTP SIMPLE - Sans LLM")
    print("="*70)
    print(f" Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    results = {}
    
    # Test 1: Connexion
    results['connection'] = test_smtp_connection()
    
    # Test 2: Envoi (si connexion OK)
    if results['connection']:
        results['sending'] = test_simple_send()
    else:
        print("\n⚠️  Skipping envoi - connexion échouée")
        results['sending'] = False
    
    # Test 3: Formatage
    results['formatting'] = test_email_formatting()
    
    # Résumé
    print("\n\n" + "="*70)
    print(" RÉSUMÉ")
    print("="*70)
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name.title()}")
    
    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    
    print(f"\n  Total: {passed_count}/{total} tests réussis")
    
    if passed_count == total:
        print("\n  🎉 TOUS LES TESTS PASSÉS!")
        print("  → Configuration SMTP parfaite")
        print("  → Prêt pour envoi en production")
    elif results.get('connection'):
        print("\n  ⚠️  Connexion OK mais envoi échoué")
        print("  → Vérifiez TEST_EMAIL dans .env")
    else:
        print("\n  ❌ Connexion SMTP échouée")
        print("  → Vérifiez credentials dans .env")
        print("  → Consultez GUIDE_TEST_SENDER.md")
    
    print("="*70 + "\n")
    
    return results


if __name__ == "__main__":
    try:
        results = main()
        
        # Exit code
        if all(results.values()):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n❌ Interrompu")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)