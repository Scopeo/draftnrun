DAT

🔹 System Architecture Overview

Frontend (Vue)
Uses Supabase Auth for user authentication.
Manages organizations, projects, and users in Supabase DB.
Uses CASL for frontend-based permission management.
Manages billing via Stripe (frontend handles customer setup, subscriptions, and payment processing).


Frontend Database (Supabase)
Users authenticate via Supabase.
Organizations & Projects stored in Postgres (Supabase).
Uses Row-Level Security (RLS) to enforce access.
Stores which users belong to which organizations in organization_members.


Backend (FastAPI)
SQLite for storing project configurations and API keys.
Does not connect to Supabase.
Authenticates users via JWT from Supabase.
Allows private key authentication for internal API usage.
Controls API key access for AI projects.
