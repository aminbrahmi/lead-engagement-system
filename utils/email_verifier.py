"""
email_verifier.py — SMTP email verification utility

Verifies if an email address exists by:
1. Checking MX records
2. Connecting to mail server
3. Simulating MAIL FROM / RCPT TO (without sending)

Auto-verifies emails from trusted sources (Hunter, FindThatLead, Apollo).
"""

import os
import smtplib
import dns.resolver
import socket
from typing import Tuple
from dotenv import load_dotenv

load_dotenv()


# Trusted email sources that don't need SMTP verification
TRUSTED_SOURCES = {
    "hunter",          # Hunter API
    "findthatlead",    # FindThatLead API
    "ftl",            # FindThatLead alias
    "apollo",         # Apollo API
}


def is_trusted_source(email_source: str) -> bool:
    """Check if email comes from a trusted API that validates emails."""
    if not email_source:
        return False
    return email_source.lower() in TRUSTED_SOURCES


def get_mx_records(domain: str) -> list:
    """Get MX records for a domain."""
    try:
        records = dns.resolver.resolve(domain, 'MX')
        return [str(r.exchange).rstrip('.') for r in sorted(records, key=lambda x: x.preference)]
    except Exception as e:
        print(f"[Verify] ⚠️ No MX records for {domain}: {e}")
        return []


def verify_email_smtp(email: str, timeout: int = 10) -> Tuple[bool, str]:
    """
    Verify if an email exists by connecting to the mail server.
    
    Returns:
        (verified: bool, message: str)
    """
    if not email or '@' not in email:
        return False, "Invalid email format"
    
    try:
        domain = email.split('@')[1]
    except IndexError:
        return False, "Invalid email format"
    
    # Get MX records
    mx_records = get_mx_records(domain)
    if not mx_records:
        return False, f"No MX records found for {domain}"
    
    # Try each MX server
    last_error = None
    
    for mx in mx_records[:3]:  # Try first 3 MX servers
        try:
            # Connect to mail server
            server = smtplib.SMTP(timeout=timeout)
            server.set_debuglevel(0)
            server.connect(mx)
            
            # EHLO
            server.ehlo()
            
            # MAIL FROM (use a valid-looking sender)
            sender = os.getenv("SMTP_USER", "verify@example.com")
            server.mail(sender)
            
            # RCPT TO (this is where verification happens)
            code, message = server.rcpt(email)
            server.quit()
            
            # 250 = OK, email exists
            # 550 = User not found
            # 451/452 = Temporary error (consider as valid)
            if code == 250:
                return True, "Email verified via SMTP"
            elif code in [451, 452]:
                # Greylisting or temporary error - assume valid
                return True, f"Email probably valid (temporary error: {code})"
            else:
                return False, f"Email rejected by server (code {code})"
                
        except smtplib.SMTPServerDisconnected:
            last_error = "Server disconnected"
            continue
        except smtplib.SMTPConnectError as e:
            last_error = f"Connection failed: {e}"
            continue
        except socket.timeout:
            last_error = "Connection timeout"
            continue
        except Exception as e:
            last_error = str(e)
            continue
    
    # All MX servers failed
    return False, f"Verification failed: {last_error}"


def verify_email(email: str, email_source: str = None) -> Tuple[bool, str]:
    """
    Main verification function with auto-verification for trusted sources.
    
    Args:
        email: Email address to verify
        email_source: Source of the email (hunter, ftl, apollo, pattern, etc.)
    
    Returns:
        (verified: bool, message: str)
    """
    if not email:
        return False, "No email provided"
    
    # Auto-verify trusted sources
    if is_trusted_source(email_source):
        return True, f"Auto-verified (trusted source: {email_source})"
    
    # SMTP verification for other sources
    print(f"[Verify] Checking {email} via SMTP...")
    verified, message = verify_email_smtp(email)
    
    if verified:
        print(f"[Verify] ✅ {email} verified")
    else:
        print(f"[Verify] ❌ {email} failed: {message}")
    
    return verified, message


def should_auto_verify(email_source: str) -> bool:
    """
    Check if this email source should be auto-verified without SMTP check.
    
    Returns True for:
    - Hunter API
    - FindThatLead API
    - Apollo API
    
    Returns False for:
    - Pattern-generated emails
    - Web scraping
    - Google search
    - Unknown sources
    """
    return is_trusted_source(email_source)


# ── Batch verification ────────────────────────────────────────────────────────

def verify_leads_batch(leads: list) -> list:
    """
    Verify all leads in batch.
    Auto-verifies trusted sources, SMTP-verifies the rest.
    
    Args:
        leads: List of lead dicts with 'email' and 'email_source'
    
    Returns:
        Updated leads with 'email_verified' field
    """
    verified_count = 0
    failed_count = 0
    auto_verified_count = 0
    
    for lead in leads:
        email = lead.get('email')
        email_source = lead.get('email_source', '')
        
        if not email:
            lead['email_verified'] = False
            continue
        
        # Skip if already verified
        if lead.get('email_verified'):
            continue
        
        # Check if should auto-verify
        if should_auto_verify(email_source):
            lead['email_verified'] = True
            auto_verified_count += 1
            print(f"[Verify] ✓ Auto-verified {email} (source: {email_source})")
        else:
            # SMTP verification
            verified, message = verify_email_smtp(email)
            lead['email_verified'] = verified
            
            if verified:
                verified_count += 1
            else:
                failed_count += 1
    
    print(f"[Verify] Batch complete: {auto_verified_count} auto-verified, "
          f"{verified_count} SMTP-verified, {failed_count} failed")
    
    return leads


# ── Test utility ──────────────────────────────────────────────────────────────

def test_verification():
    """Test email verification with various sources."""
    test_cases = [
        ("john@google.com", "hunter"),        # Should auto-verify
        ("test@gmail.com", "pattern"),        # Should SMTP verify
        ("invalid@fakefake.com", "ftl"),      # Should auto-verify (trusted)
        ("bad@nonexistent.xyz", "web"),       # Should SMTP verify (will fail)
    ]
    
    print("\n" + "="*70)
    print(" EMAIL VERIFICATION TEST")
    print("="*70 + "\n")
    
    for email, source in test_cases:
        print(f"\nTesting: {email} (source: {source})")
        verified, message = verify_email(email, source)
        status = "✅ VERIFIED" if verified else "❌ FAILED"
        print(f"  {status}: {message}")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    test_verification()