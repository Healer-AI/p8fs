-- Fuzzy search stored procedure for TiDB
-- Table-agnostic fuzzy text search for REM queries
-- Supports FTS_MATCH_WORD (with FULLTEXT indexes) or LIKE fallback

DELIMITER $$

DROP PROCEDURE IF EXISTS p8.fuzzy_search$$

CREATE PROCEDURE p8.fuzzy_search(
    IN p_table_name VARCHAR(255),
    IN p_search_fields JSON,
    IN p_query_text TEXT,
    IN p_tenant_id VARCHAR(255),
    IN p_similarity_threshold FLOAT,
    IN p_max_results INT,
    IN p_use_word_similarity BOOLEAN
)
BEGIN
    /*
    Table-agnostic fuzzy text search for TiDB.

    Two modes:
    1. Full-text search (p_use_word_similarity=true): Uses FTS_MATCH_WORD with BM25 scoring
    2. LIKE fallback (p_use_word_similarity=false): Case-insensitive substring matching

    Parameters:
    - p_table_name: Target table (e.g., 'resources', 'moments')
    - p_search_fields: JSON array of field names (e.g., '["name", "content"]')
    - p_query_text: Search text
    - p_tenant_id: Tenant filter (required)
    - p_similarity_threshold: Minimum score (ignored in LIKE mode)
    - p_max_results: Result limit
    - p_use_word_similarity: true=FTS, false=LIKE

    Examples:
    -- FTS mode (requires FULLTEXT indexes)
    CALL p8.fuzzy_search(
        'resources',
        '["name"]',
        'afternoon',
        'tenant-test',
        0.1,
        5,
        true
    );

    -- LIKE mode (no indexes required)
    CALL p8.fuzzy_search(
        'resources',
        '["name", "content"]',
        'design',
        'tenant-test',
        0,
        10,
        false
    );

    Returns:
    - SELECT result with JSON objects containing row data + similarity_score
    */

    DECLARE v_sql TEXT;
    DECLARE v_field_count INT;
    DECLARE v_field_name VARCHAR(255);
    DECLARE v_field_conditions TEXT DEFAULT '';
    DECLARE v_score_expressions TEXT DEFAULT '';
    DECLARE v_order_clause TEXT;
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_like_pattern TEXT;

    -- Get field count
    SET v_field_count = JSON_LENGTH(p_search_fields);

    IF p_use_word_similarity THEN
        -- Mode 1: Full-text search with FTS_MATCH_WORD
        WHILE v_i < v_field_count DO
            SET v_field_name = JSON_UNQUOTE(JSON_EXTRACT(p_search_fields, CONCAT('$[', v_i, ']')));

            IF v_i > 0 THEN
                SET v_field_conditions = CONCAT(v_field_conditions, ' OR ');
                SET v_score_expressions = CONCAT(v_score_expressions, ', ');
            END IF;

            SET v_field_conditions = CONCAT(
                v_field_conditions,
                'FTS_MATCH_WORD(?, ', v_field_name, ') > 0'
            );
            SET v_score_expressions = CONCAT(
                v_score_expressions,
                'FTS_MATCH_WORD(?, ', v_field_name, ')'
            );

            SET v_i = v_i + 1;
        END WHILE;

        -- Build dynamic SQL for FTS mode
        SET v_sql = CONCAT(
            'SELECT CAST(CONCAT(''{',
            'CONCAT_WS('','', ',
                'CONCAT(''"id":"'', COALESCE(CONCAT(''"'', id, ''"''), ''null''), ''"''), ',
                'CONCAT(''"name":"'', COALESCE(CONCAT(''"'', REPLACE(name, ''"'', ''\"''), ''"''), ''null''), ''"''), ',
                'CONCAT(''"tenant_id":"'', COALESCE(CONCAT(''"'', tenant_id, ''"''), ''null''), ''"''), ',
                'CONCAT(''"similarity_score":'', GREATEST(', v_score_expressions, '))',
            '),',
            '''}'')',
            ' AS JSON) as result ',
            'FROM ', p_table_name, ' ',
            'WHERE tenant_id = ? ',
            'AND (', v_field_conditions, ') ',
            'ORDER BY GREATEST(', v_score_expressions, ') DESC ',
            'LIMIT ?'
        );

        -- Note: This requires PREPARE/EXECUTE which TiDB supports
        -- For now, return error suggesting to use LIKE mode
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'FTS mode not yet implemented via stored procedure. Use LIKE mode (use_word_similarity=false) or call directly from application.';

    ELSE
        -- Mode 2: LIKE fallback (case-insensitive)
        SET v_like_pattern = CONCAT('%', LOWER(p_query_text), '%');

        WHILE v_i < v_field_count DO
            SET v_field_name = JSON_UNQUOTE(JSON_EXTRACT(p_search_fields, CONCAT('$[', v_i, ']')));

            IF v_i > 0 THEN
                SET v_field_conditions = CONCAT(v_field_conditions, ' OR ');
            END IF;

            SET v_field_conditions = CONCAT(
                v_field_conditions,
                'LOWER(', v_field_name, ') LIKE ?'
            );

            SET v_i = v_i + 1;
        END WHILE;

        -- Get first field for ORDER BY priority
        SET v_field_name = JSON_UNQUOTE(JSON_EXTRACT(p_search_fields, '$[0]'));

        SET v_order_clause = CONCAT(
            'CASE ',
                'WHEN LOWER(', v_field_name, ') = LOWER(?) THEN 1 ',
                'WHEN LOWER(', v_field_name, ') LIKE ? THEN 2 ',
                'ELSE 3 ',
            'END'
        );

        -- Build dynamic SQL for LIKE mode
        -- Note: TiDB stored procedures have limitations with dynamic SQL and JSON
        -- For now, return error suggesting direct application call
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'TiDB stored procedure fuzzy search not yet fully implemented. Use inline SQL from application for now.';
    END IF;
END$$

DELIMITER ;

-- Note: TiDB stored procedures have limitations compared to PostgreSQL functions:
-- 1. Dynamic SQL requires PREPARE/EXECUTE which is complex with parameterized queries
-- 2. JSON construction is more verbose than PostgreSQL's to_jsonb()
-- 3. Cannot easily return table results from dynamic SQL
--
-- Recommendation: Keep TiDB fuzzy search as inline SQL in application layer
-- until TiDB improves stored procedure capabilities or we implement a workaround.
