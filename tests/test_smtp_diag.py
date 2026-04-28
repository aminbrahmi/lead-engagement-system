#!/usr/bin/env python3
"""
Test SMTP diagnostique - trouve exactement où ça bloque
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
load_dotenv()

print("\n" + "="*70)
print(" DIAGNOSTIC SMTP - Gmail")
print("="*70 + "\n")

# Configuration
smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
smtp_user = os.getenv("SMTP_USER")
smtp_password = os.getenv("SMTP_PASS")
test_email = os.getenv("TEST_EMAIL", smtp_user)

print("📋 Configuration:")
print(f"   Host: {smtp_host}")
print(f"   User: {smtp_user}")
print(f"   Password: {'*' * len(smtp_password) if smtp_password else 'MANQUANT'}")
print(f"   Test email: {test_email}")
print()

if not smtp_user or not smtp_password:
    print("❌ ERREUR: SMTP_USER ou SMTP_PASSWORD manquant dans .env")
    sys.exit(1)

# Test 1: Port 587 (TLS)
print("="*70)
print("TEST 1: Port 587 avec STARTTLS")
print("="*70)

try:
    print("→ Connexion à smtp.gmail.com:587...")
    server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
    print("✅ Connexion établie")
    
    print("→ EHLO...")
    server.ehlo()
    print("✅ EHLO OK")
    
    print("→ STARTTLS...")
    server.starttls()
    print("✅ STARTTLS OK")
    
    print("→ EHLO après TLS...")
    server.ehlo()
    print("✅ EHLO après TLS OK")
    
    print("→ Authentification...")
    server.login(smtp_user, smtp_password)
    print("✅ AUTHENTIFICATION RÉUSSIE!")
    
    print("→ Envoi d'un email de test...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Test SMTP - Lead Engagement System"
    msg['From'] = smtp_user
    msg['To'] = test_email
    
    html = f"""
    <html>
      <body>
        <h2>✅ Test SMTP Réussi!</h2>
        <p>Votre configuration SMTP fonctionne parfaitement.</p>
        <p><strong>Port:</strong> 587 (STARTTLS)</p>
        <p><strong>De:</strong> {smtp_user}</p>
        <p><strong>À:</strong> {test_email}</p>
        <hr>
        <p><small>Lead Engagement System - Test automatique</small></p>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(html, 'html'))
    
    server.send_message(msg)
    print("✅ EMAIL ENVOYÉ!")
    
    server.quit()
    print("\n" + "="*70)
    print("🎉 SUCCÈS TOTAL - Port 587 fonctionne!")
    print("="*70)
    print("\n✅ Votre configuration SMTP est correcte.")
    print("✅ Vérifiez votre boîte mail:", test_email)
    sys.exit(0)
    
except smtplib.SMTPAuthenticationError as e:
    print(f"\n❌ ERREUR D'AUTHENTIFICATION")
    print(f"   Détails: {e}")
    print("\n💡 SOLUTION:")
    print("   1. Vous utilisez probablement votre mot de passe Gmail normal")
    print("   2. Gmail EXIGE un 'App Password' pour les applications tierces")
    print("\n📝 CRÉER UN APP PASSWORD:")
    print("   1. Activez la validation en 2 étapes: https://myaccount.google.com/security")
    print("   2. Créez un App Password: https://myaccount.google.com/apppasswords")
    print("   3. Copiez le mot de passe (format: xxxx xxxx xxxx xxxx)")
    print("   4. Dans .env, remplacez SMTP_PASSWORD par ce mot de passe (sans espaces)")
    print("\n   Exemple dans .env:")
    print("   SMTP_PASSWORD=abcdefghijklmnop")
    
except Exception as e:
    print(f"\n❌ ERREUR Port 587: {e}")
    print(f"   Type: {type(e).__name__}")

# Test 2: Port 465 (SSL)
print("\n" + "="*70)
print("TEST 2: Port 465 avec SSL")
print("="*70)

try:
    print("→ Connexion à smtp.gmail.com:465...")
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
    print("✅ Connexion SSL établie")
    
    print("→ EHLO...")
    server.ehlo()
    print("✅ EHLO OK")
    
    print("→ Authentification...")
    server.login(smtp_user, smtp_password)
    print("✅ AUTHENTIFICATION RÉUSSIE!")
    
    print("→ Envoi d'un email de test...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Test SMTP - Lead Engagement System (Port 465)"
    msg['From'] = smtp_user
    msg['To'] = test_email
    
    html = f"""
    <html>
      <body>
        <h2>✅ Test SMTP Réussi!</h2>
        <p>Votre configuration SMTP fonctionne parfaitement.</p>
        <p><strong>Port:</strong> 465 (SSL)</p>
        <p><strong>De:</strong> {smtp_user}</p>
        <p><strong>À:</strong> {test_email}</p>
        <hr>
        <p><small>Lead Engagement System - Test automatique</small></p>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(html, 'html'))
    
    server.send_message(msg)
    print("✅ EMAIL ENVOYÉ!")
    
    server.quit()
    print("\n" + "="*70)
    print("🎉 SUCCÈS TOTAL - Port 465 fonctionne!")
    print("="*70)
    print("\n✅ Votre configuration SMTP est correcte.")
    print("✅ Vérifiez votre boîte mail:", test_email)
    print("\n💡 RECOMMANDATION:")
    print("   Dans votre .env, utilisez:")
    print("   SMTP_PORT=465")
    print("   SMTP_USE_SSL=true")
    sys.exit(0)
    
except smtplib.SMTPAuthenticationError as e:
    print(f"\n❌ ERREUR D'AUTHENTIFICATION")
    print(f"   Détails: {e}")
    print("\n💡 SOLUTION:")
    print("   Gmail EXIGE un 'App Password' - voir instructions ci-dessus")
    
except Exception as e:
    print(f"\n❌ ERREUR Port 465: {e}")
    print(f"   Type: {type(e).__name__}")

# Résumé
print("\n" + "="*70)
print("❌ ÉCHEC DES DEUX PORTS")
print("="*70)

print("\n🔍 PROBLÈME PROBABLE:")
print("   Vous n'utilisez PAS un App Password Gmail")

print("\n✅ SOLUTION EN 3 ÉTAPES:")
print("\n1️⃣  Activer la validation en 2 étapes:")
print("   → https://myaccount.google.com/security")
print("   → Cherchez 'Validation en deux étapes'")
print("   → Activez-la")

print("\n2️⃣  Créer un App Password:")
print("   → https://myaccount.google.com/apppasswords")
print("   → Nom: 'Lead Engagement System'")
print("   → Copiez le mot de passe (16 caractères)")

print("\n3️⃣  Mettre à jour .env:")
print("   Ouvrez: .env")
print("   Remplacez:")
print("   SMTP_PASSWORD=votre_mot_de_passe_normal")
print("   Par:")
print("   SMTP_PASSWORD=abcdefghijklmnop  (votre App Password sans espaces)")

print("\n4️⃣  Retestez:")
print("   python test_smtp_diagnostic.py")

print("\n" + "="*70)