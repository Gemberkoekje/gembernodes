-- Home Assistant's recorder database and login on the shared PostgreSQL (README.md, step 1), for
-- DBeaver. Connect as postgres to the database "postgres" on 192.168.1.232:5432, with auto-commit
-- ON: CREATE DATABASE refuses to run inside a transaction.
--
-- 1. Run this one statement (Ctrl+Enter) and copy the password it makes: 64 hex characters from
--    PostgreSQL's strong random generator. Hex keeps the database URL valid.

SELECT replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '') AS password;

-- 2. Paste it between the quotes below, then run the rest of the script (Alt+X from here, or
--    select the rest and Alt+X). The block refuses to run with anything but a hex password, so a
--    forgotten paste stops here instead of creating a login with a known password.

DO $$
DECLARE
    password text := 'PASTE-THE-PASSWORD-HERE';
BEGIN
    IF password !~ '^[0-9a-f]{48,}$' THEN
        RAISE EXCEPTION 'Paste the password from step 1 into the script first.';
    END IF;

    -- Not a superuser, can't create databases or roles (the defaults).
    EXECUTE format('CREATE ROLE homeassistant LOGIN PASSWORD %L', password);
END
$$;

CREATE DATABASE homeassistant OWNER homeassistant;

-- Every login may connect to a new database; only homeassistant may connect to this one.
REVOKE CONNECT, TEMPORARY ON DATABASE homeassistant FROM PUBLIC;

-- 3. Check: a login that is no superuser and can't create databases or roles, owning a database
--    that PUBLIC may not connect to (datacl without "=c").

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
FROM pg_roles
WHERE rolname = 'homeassistant';

SELECT datname, pg_get_userbyid(datdba) AS owner, datacl
FROM pg_database
WHERE datname = 'homeassistant';

-- 4. The 1Password item "homeassistant-secrets" (Gembercluster vault), field label exactly
--    RECORDER_DB_URL, value:
--
--    postgresql://homeassistant:<the password from step 1>@postgresql.flux-system.svc.cluster.local:5432/homeassistant
--
--    Home Assistant creates its own tables at its first start.

-- Undo, should you need to start over (Home Assistant must not be running; with auto-commit on, as
-- each must run on its own):
--
-- DROP DATABASE homeassistant;
-- DROP ROLE homeassistant;
