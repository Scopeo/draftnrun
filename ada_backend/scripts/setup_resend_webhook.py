#!/usr/bin/env python
"""
Script to set up Resend webhook configurations and link them to projects.
Run with: python -m ada_backend.scripts.setup_resend_webhook

Example usage:
    python -m ada_backend.scripts.setup_resend_webhook \
        --create \
        --organization-id 550e8400-e29b-41d4-a716-446655440000 \
        --signing-secret whsec_xxxxxxxxxxxxx \
        --project-id 650e8400-e29b-41d4-a716-446655440000 \
        --recipient-email support@mydomain.com
"""

import argparse
import hashlib
import json
import sys
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from ada_backend.database.models import IntegrationTrigger, Webhook, WebhookProvider
from ada_backend.database.setup_db import SessionLocal
from settings import settings


def generate_events_hash(events: dict) -> str:
    """Generate SHA256 hash of events for IntegrationTrigger."""
    events_json = json.dumps(events or {}, sort_keys=True)
    return hashlib.sha256(events_json.encode()).hexdigest()


def list_webhooks():
    """List all existing Resend webhooks."""
    print("\n=== Resend Webhooks ===\n")

    session = SessionLocal()
    try:
        webhooks = session.query(Webhook).filter(Webhook.provider == WebhookProvider.RESEND).all()

        if not webhooks:
            print("No Resend webhooks found.")
            return True

        print(f"Found {len(webhooks)} Resend webhook(s):\n")
        for webhook in webhooks:
            print(f"Webhook ID: {webhook.id}")
            print(f"Organization ID: {webhook.organization_id}")
            print(f"Signing Secret: {webhook.external_client_id[:10]}...")
            print(f"Created: {webhook.created_at}")

            triggers = (
                session.query(IntegrationTrigger)
                .filter(IntegrationTrigger.webhook_id == webhook.id)
                .all()
            )

            if triggers:
                print(f"Triggers ({len(triggers)}):")
                for trigger in triggers:
                    status = "enabled" if trigger.enabled else "disabled"
                    print(f"  - Trigger ID: {trigger.id}")
                    print(f"    Project ID: {trigger.project_id}")
                    print(f"    Status: {status}")
                    print(f"    Events: {trigger.events or 'all'}")
                    filter_options = trigger.filter_options or {}
                    if filter_options.get("recipient_email"):
                        print(f"    Recipient: {filter_options['recipient_email']}")
            else:
                print("Triggers: None")

            print()

    except SQLAlchemyError as e:
        print(f"ERROR: Failed to list webhooks: {str(e)}")
        return False
    finally:
        session.close()

    return True


def delete_webhook(webhook_id: str):
    """Delete a Resend webhook and all its triggers."""
    print("\n=== Deleting Resend Webhook ===\n")

    try:
        webhook_uuid = UUID(webhook_id)
    except ValueError as e:
        print(f"ERROR: Invalid webhook ID format: {str(e)}")
        return False

    session = SessionLocal()
    try:
        webhook = (
            session.query(Webhook)
            .filter(Webhook.id == webhook_uuid, Webhook.provider == WebhookProvider.RESEND)
            .first()
        )

        if not webhook:
            print(f"ERROR: Webhook not found with ID: {webhook_id}")
            return False

        # Get trigger count before deletion
        trigger_count = (
            session.query(IntegrationTrigger)
            .filter(IntegrationTrigger.webhook_id == webhook.id)
            .count()
        )

        print(f"Webhook ID: {webhook.id}")
        print(f"Organization ID: {webhook.organization_id}")
        print(f"Linked triggers: {trigger_count}")
        print()

        response = input("Are you sure you want to delete this webhook? (yes/no): ")
        if response.lower() != "yes":
            print("Cancelled.")
            return False

        session.delete(webhook)
        session.commit()

        print(f"✅ Deleted webhook: {webhook.id}")
        if trigger_count > 0:
            print(f"   Also deleted {trigger_count} linked trigger(s)")

        return True

    except SQLAlchemyError as e:
        session.rollback()
        print(f"ERROR: Database error: {str(e)}")
        return False
    finally:
        session.close()


def create_webhook(
    organization_id: str, signing_secret: str, project_id: str, events: dict = None, recipient_email: str = None
):
    """Create a new Resend webhook and link it to a project."""
    print("\n=== Creating Resend Webhook ===\n")

    if not signing_secret.startswith("whsec_"):
        print("WARNING: Signing secret should start with 'whsec_'")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled.")
            return False

    try:
        org_uuid = UUID(organization_id)
        proj_uuid = UUID(project_id)
    except ValueError as e:
        print(f"ERROR: Invalid UUID format: {str(e)}")
        return False

    session = SessionLocal()
    try:
        existing = (
            session.query(Webhook)
            .filter(
                Webhook.provider == WebhookProvider.RESEND,
                Webhook.external_client_id == signing_secret
            )
            .first()
        )

        if existing:
            print(f"Webhook with this signing secret already exists: {existing.id}")
            print("Using existing webhook...")
            webhook = existing
        else:
            webhook = Webhook(
                organization_id=org_uuid,
                provider=WebhookProvider.RESEND,
                external_client_id=signing_secret,
            )
            session.add(webhook)
            session.flush()
            print(f"✅ Created webhook: {webhook.id}")

        existing_trigger = (
            session.query(IntegrationTrigger)
            .filter(
                IntegrationTrigger.webhook_id == webhook.id,
                IntegrationTrigger.project_id == proj_uuid
            )
            .first()
        )

        if existing_trigger:
            print(f"Trigger for this webhook and project already exists: {existing_trigger.id}")
            print(f"Status: {'enabled' if existing_trigger.enabled else 'disabled'}")
        else:
            events_hash = generate_events_hash(events)

            # TODO: Enable users to design custom filter_options via UI/API instead of hardcoded CLI creation
            filter_options = None
            if recipient_email:
                filter_options = {
                    "operator": "OR",
                    "conditions": [
                        {"field": "to", "operator": "contains", "value": recipient_email},
                        {"field": "cc", "operator": "contains", "value": recipient_email},
                        {"field": "bcc", "operator": "contains", "value": recipient_email},
                    ]
                }

            trigger = IntegrationTrigger(
                webhook_id=webhook.id,
                project_id=proj_uuid,
                events=events,
                events_hash=events_hash,
                enabled=True,
                filter_options=filter_options if filter_options else None,
            )
            session.add(trigger)
            session.flush()
            print(f"✅ Created integration trigger: {trigger.id}")
            print(f"   Linked to project: {proj_uuid}")
            print(f"   Events filter: {events or 'all events'}")
            if recipient_email:
                print(f"   Recipient filter: {recipient_email}")

        session.commit()

        print("\n=== Setup Complete ===\n")
        print(f"Webhook ID: {webhook.id}")
        print(f"Organization ID: {organization_id}")

        base_url = settings.ADA_URL or "https://ada-prod.scopeo.studio"
        webhook_url = f"{base_url}/webhooks/resend"
        print(f"\nWebhook URL: {webhook_url}")
        print("\nConfigure this URL in your Resend dashboard.")
        print("The webhook will trigger the linked project when emails are received.")

        return True

    except SQLAlchemyError as e:
        session.rollback()
        print(f"ERROR: Failed to create webhook: {str(e)}")
        return False
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Set up Resend webhook configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all Resend webhooks
  python -m ada_backend.scripts.setup_resend_webhook --list

  # Create a new webhook
  python -m ada_backend.scripts.setup_resend_webhook \\
      --create \\
      --organization-id 550e8400-e29b-41d4-a716-446655440000 \\
      --signing-secret whsec_xxxxxxxxxxxxx \\
      --project-id 650e8400-e29b-41d4-a716-446655440000

  # Create with recipient email filter (only triggers for emails to this address)
  python -m ada_backend.scripts.setup_resend_webhook \\
      --create \\
      --organization-id 550e8400-e29b-41d4-a716-446655440000 \\
      --signing-secret whsec_xxxxxxxxxxxxx \\
      --project-id 650e8400-e29b-41d4-a716-446655440000 \\
      --recipient-email support@mydomain.com

  # Delete a webhook (also deletes all linked triggers)
  python -m ada_backend.scripts.setup_resend_webhook \\
      --delete \\
      --webhook-id 550e8400-e29b-41d4-a716-446655440000
        """
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all existing Resend webhooks"
    )

    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new Resend webhook"
    )

    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete a Resend webhook and all its triggers"
    )

    parser.add_argument(
        "--webhook-id",
        type=str,
        help="Webhook UUID (required for --delete)"
    )

    parser.add_argument(
        "--organization-id",
        type=str,
        help="Organization UUID (required for --create)"
    )

    parser.add_argument(
        "--signing-secret",
        type=str,
        help="Resend/Svix signing secret (starts with whsec_) (required for --create)"
    )

    parser.add_argument(
        "--project-id",
        type=str,
        help="Project UUID to link the webhook to (required for --create)"
    )

    parser.add_argument(
        "--events",
        type=str,
        help="Events filter as JSON (optional, defaults to all events)"
    )

    parser.add_argument(
        "--recipient-email",
        type=str,
        help="Filter by recipient email address (to/cc/bcc). Only trigger workflow when this email receives mail."
    )

    args = parser.parse_args()

    if not args.list and not args.create and not args.delete:
        parser.print_help()
        sys.exit(1)

    if args.list:
        success = list_webhooks()
        sys.exit(0 if success else 1)

    if args.delete:
        if not args.webhook_id:
            print("ERROR: --webhook-id is required for --delete")
            sys.exit(1)

        success = delete_webhook(args.webhook_id)
        sys.exit(0 if success else 1)

    if args.create:
        if not args.organization_id:
            print("ERROR: --organization-id is required for --create")
            sys.exit(1)

        if not args.signing_secret:
            print("ERROR: --signing-secret is required for --create")
            sys.exit(1)

        if not args.project_id:
            print("ERROR: --project-id is required for --create")
            sys.exit(1)

        events = None
        if args.events:
            try:
                events = json.loads(args.events)
            except json.JSONDecodeError as e:
                print(f"ERROR: Invalid JSON in --events: {str(e)}")
                sys.exit(1)

        success = create_webhook(
            organization_id=args.organization_id,
            signing_secret=args.signing_secret,
            project_id=args.project_id,
            events=events,
            recipient_email=args.recipient_email
        )
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
