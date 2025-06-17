# **Alembic - Database Migrations for SQLAlchemy**

## 📌 **What is Alembic?**

Alembic is a **database migration tool** for SQLAlchemy. It allows us to:

- Track changes to our database schema over time.
- Apply those changes in a structured, version-controlled manner.
- Roll back changes if needed.

Think of Alembic like **Git for your database**—it helps us manage **schema changes** safely and consistently across different environments (development, staging, production).

---

## 🚀 **Why Do We Need Alembic?**

When working with a database, schema changes happen over time:

- New tables get added.
- Columns are modified or removed.
- Constraints and indexes change.

Instead of manually applying these changes, **Alembic generates migration scripts** that ensure every team member and environment stays in sync. This is especially important in **CI/CD pipelines** where migrations must run automatically.

---

## 📖 **How Alembic Works (Compared to Git)**

If you know Git, Alembic will feel familiar:

| **Git** 🛠                 | **Alembic** 🏗                   |
| ------------------------- | ------------------------------- |
| `git init`                | `alembic init alembic`          |
| `git commit -m "message"` | `alembic revision -m "message"` |
| `git push`                | `alembic upgrade head`          |
| `git log`                 | `alembic history`               |
| `git checkout <commit>`   | `alembic downgrade <revision>`  |
| `git diff`                | `alembic current`               |

Each Alembic **revision** is like a Git commit—it has a unique ID and tracks the exact schema changes at that point.

---

## 🔄 **Alembic Workflow**

Here’s the typical workflow we follow when modifying the database schema:

### 1️⃣ **Make Schema Changes**

Modify your SQLAlchemy models, e.g.:

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String, unique=True)  # <-- Adding a new column
```

### 2️⃣ **Generate a Migration Script**

Run:

```sh
alembic revision --autogenerate -m "Added email column to users"
```

This creates a new file inside `alembic/versions/`, containing the **exact SQL changes** needed.

### 3️⃣ **Review & Apply the Migration**

Check the migration script before applying it, then run:

```sh
alembic upgrade head
```

This updates the database to the latest version.

### 4️⃣ **Commit the Migration**

Once everything works, **commit both your code and migration**:

```sh
git add models.py alembic/versions/<migration_file>.py
git commit -m "Added email column to users"
```

This ensures that future deployments apply the same database changes.

---

## 🚦 **Best Practices for Using Alembic**

✅ **Developers are responsible for creating migrations**  
Every time you change a model, generate and commit a migration.

✅ **CI/CD should apply pending migrations automatically**  
Before running the app in staging/production, execute:

```sh
alembic upgrade head
```

✅ **Check for missing migrations in CI**  
Ensure that all schema changes have a corresponding migration:

```sh
alembic revision --autogenerate -m "Check for missing migrations" --raiseerr
```

✅ **Use feature flags for risky changes**  
Instead of dropping columns instantly, use a feature flag to phase out old fields.

✅ **Rollback mechanism for production failures**  
If something goes wrong, rollback to a previous version:

```sh
alembic downgrade -1  # Goes back one migration
```

---

## 🔗 **Tracking Alembic Versions with Git (Optional)**

Alembic **does not automatically track migrations in Git**, so we can manually enforce version tracking by:

1. **Storing the current Alembic version in a file**

   ```sh
   alembic current > alembic_version.txt
   git add alembic_version.txt
   ```

2. **Tagging database versions**
   ```sh
   git tag -a alembic_<revision_id> -m "Database version for this release"
   ```

This helps when rolling back to a specific commit—just check `alembic_version.txt` and run:

```sh
alembic downgrade <revision_id>
```

---

## 📌 **Useful Alembic Commands**

| Command                                        | Description                               |
| ---------------------------------------------- | ----------------------------------------- |
| `alembic init alembic`                         | Initialize Alembic in the project         |
| `alembic revision -m "message"`                | Create a new migration (empty)            |
| `alembic revision --autogenerate -m "message"` | Create a migration based on model changes |
| `alembic upgrade head`                         | Apply all pending migrations              |
| `alembic downgrade -1`                         | Revert the last migration                 |
| `alembic history`                              | Show migration history                    |
| `alembic current`                              | Show the current migration version        |
| `alembic check`                                | Check if migrations need to be applied    |

---

## 🎯 **Final Thoughts**

Alembic **ensures our database schema evolves safely**. By following this workflow, we:

- Keep all environments in sync.
- Automate migrations in CI/CD.
- Maintain version history for easy rollbacks.

If you have questions, check out [Alembic’s official documentation](https://alembic.sqlalchemy.org/en/latest/) or ask the team! 🚀
