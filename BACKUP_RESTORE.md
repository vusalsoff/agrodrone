# AgroDrone Backup, Restore & Migration Rollback Guide

## 1. PostgreSQL 16 Backup (Docker / Managed)

### Logical Backup (`pg_dump`)
```powershell
$stamp = Get-Date -Format "yyyyMMddTHHmmssZ"
docker exec agrodrone-postgres pg_dump -U agrodrone -Fc agrodrone > "agrodrone_backup_$stamp.dump"
```

### Restore (`pg_restore`)
```powershell
docker exec -i agrodrone-postgres pg_restore -U agrodrone -d agrodrone --clean --if-exists < agrodrone_backup_20261119T120000Z.dump
```

> For managed PostgreSQL (RDS / Cloud SQL / Neon), enable automated point-in-time recovery (PITR) and take a manual snapshot before every migration.

---

## 2. Alembic Migration Rollback Strategy

1. Check current revision before migrating:
   ```powershell
   alembic current
   ```
2. Apply forward migration:
   ```powershell
   alembic upgrade head
   ```
3. If an application release fails immediately after migration, **do not run destructive downgrades blindly on live data** unless verified safe:
   - Prefer restoring the pre-migration PostgreSQL snapshot if data was transformed.
   - For schema-only rollback to a specific revision:
     ```powershell
     alembic downgrade 0004_phase4_edge_gateway
     ```

---

## 3. Private S3 / MinIO Media Backups

- Enable **Bucket Versioning** on your production S3 bucket so accidental overwrites or deletes can be recovered.
- Enforce `infra/s3/lifecycle-policy-example.json` to abort incomplete multipart uploads after 2 days and transition media older than 90 days to Infrequent Access.
- Never sync production media to local developer laptops without anonymization and explicit authorization.
