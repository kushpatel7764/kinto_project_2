CREATE OR REPLACE FUNCTION from_epoch(epoch BIGINT) RETURNS TIMESTAMP AS $$
DECLARE
    base TIMESTAMP := TIMESTAMP '2020-01-01 00:00:00';
BEGIN
    RETURN base + (epoch * INTERVAL '10 microseconds');
END;
$$ LANGUAGE plpgsql
IMMUTABLE;



CREATE OR REPLACE FUNCTION bump_timestamp()
RETURNS trigger AS $$
DECLARE
    previous TIMESTAMP;
    current TIMESTAMP;

BEGIN
    --
    -- This bumps the current timestamp to 1 msec in the future if the previous
    -- timestamp is equal to the current one (or higher if was bumped already).
    --
    -- If a bunch of requests from the same user on the same collection
    -- arrive in the same millisecond, the unicity constraint can raise
    -- an error (operation is cancelled).
    -- See https://github.com/mozilla-services/cliquet/issues/25
    --
    previous := collection_timestamp(NEW.parent_id, NEW.collection_id);

    IF NEW.last_modified IS NULL THEN
        current := clock_timestamp();
        IF previous >= current THEN
            current := previous + INTERVAL '10 microseconds';
        END IF;
        NEW.last_modified := current;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- Bump storage schema version.
INSERT INTO metadata (name, value) VALUES ('storage_schema_version', '9');
