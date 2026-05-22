"""
setup_sender.py - Configure SMTP sender for email sending

Run this once to setup your sender configuration.
"""

import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from memory.storage import save_sender_config

def setup_sender():
    """Create sender configuration in database."""
    
    print("\n" + "="*70)
    print(" SENDER CONFIGURATION SETUP")
    print("="*70 + "\n")
    
    # Your sender information
    sender_data = {
        "name": "Amine Brahmi",
        "email": "aminebrahmity12@gmail.com",
        "title": "Growth Lead",
        "company": "TALAN",
        "company_description": "Global consulting firm specializing in AI and digital transformation",
        "company_url": "https://talan.com",
        "company_location": "Paris, France",
        "company_size": "5000+ employees",
        "is_default": True
    }
    
    print("Creating sender configuration:")
    print(f"  Name:    {sender_data['name']}")
    print(f"  Email:   {sender_data['email']}")
    print(f"  Title:   {sender_data['title']}")
    print(f"  Company: {sender_data['company']}")
    print()
    
    # Save to database
    try:
        save_sender_config(**sender_data)
        print("✅ Sender configuration saved successfully!")
        print()
        print("You can now send emails from the interface.")
        print()
        
    except Exception as e:
        print(f"❌ Error saving configuration: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = setup_sender()
    
    if success:
        print("="*70)
        print(" NEXT STEPS")
        print("="*70)
        print()
        print("1. Make sure your .env file has SMTP settings:")
        print("   SMTP_HOST=smtp.gmail.com")
        print("   SMTP_PORT=587")
        print("   SMTP_USER=aminebrahmity12@gmail.com")
        print("   SMTP_PASSWORD=your_app_password_here")
        print()
        print("2. Restart your backend server")
        print()
        print("3. Try sending an email again!")
        print()
    
    sys.exit(0 if success else 1)