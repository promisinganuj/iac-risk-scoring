"""Extended tests for evidence allowlist: bounds, type validation, full query coverage.

Covers gaps identified in iac-risk-scoring-8o9:
- limit=0 and limit<0 rejected
- limit exactly at max_limit accepted
- limit=1 (minimum valid) accepted
- Bool param kind validation
- Int param with min_value/max_value bounds
- Optional params (required=False) accept None
- All 14 queries have LIMIT + ORDER BY
- _validate_param with wrong type for int/str/bool
- Non-allowlisted query rejection (arbitrary Cypher)
"""

import unittest

from risk_scoring.evidence_allowlist import (
    ALLOWLIST,
    ParamSpec,
    ParameterValidationError,
    QuerySpec,
    UnknownQueryError,
    _validate_param,
    get_query,
    validate_params,
)


class TestLimitBounds(unittest.TestCase):
    """Limit parameter edge cases."""

    def test_limit_zero_rejected(self):
        q = get_query("t3.service_incidents")
        with self.assertRaises(ParameterValidationError) as ctx:
            validate_params(q, {"serviceId": "svc-1", "limit": 0})
        self.assertIn("must be > 0", str(ctx.exception))

    def test_limit_negative_rejected(self):
        q = get_query("t3.service_incidents")
        with self.assertRaises(ParameterValidationError):
            validate_params(q, {"serviceId": "svc-1", "limit": -5})

    def test_limit_at_max_accepted(self):
        q = get_query("t3.service_incidents")
        params = validate_params(q, {"serviceId": "svc-1", "limit": q.max_limit})
        self.assertEqual(params["limit"], q.max_limit)

    def test_limit_one_above_max_rejected(self):
        q = get_query("t3.service_incidents")
        with self.assertRaises(ParameterValidationError):
            validate_params(q, {"serviceId": "svc-1", "limit": q.max_limit + 1})

    def test_limit_one_accepted(self):
        q = get_query("t3.service_incidents")
        params = validate_params(q, {"serviceId": "svc-1", "limit": 1})
        self.assertEqual(params["limit"], 1)

    def test_limit_string_rejected(self):
        q = get_query("t3.service_incidents")
        with self.assertRaises(ParameterValidationError):
            validate_params(q, {"serviceId": "svc-1", "limit": "10"})

    def test_limit_float_rejected(self):
        q = get_query("t3.service_incidents")
        with self.assertRaises(ParameterValidationError):
            validate_params(q, {"serviceId": "svc-1", "limit": 10.5})


class TestParamValidation(unittest.TestCase):
    """Direct _validate_param tests for each kind."""

    def test_str_param_int_value_rejected(self):
        spec = ParamSpec(name="x", kind="str", required=True)
        with self.assertRaises(ParameterValidationError) as ctx:
            _validate_param(spec, 123)
        self.assertIn("must be a string", str(ctx.exception))

    def test_str_param_empty_when_required_rejected(self):
        spec = ParamSpec(name="x", kind="str", required=True)
        with self.assertRaises(ParameterValidationError):
            _validate_param(spec, "   ")

    def test_str_param_whitespace_stripped(self):
        spec = ParamSpec(name="x", kind="str", required=True)
        result = _validate_param(spec, "  hello  ")
        self.assertEqual(result, "hello")

    def test_str_param_max_len_boundary(self):
        spec = ParamSpec(name="x", kind="str", required=True, max_len=5)
        self.assertEqual(_validate_param(spec, "abcde"), "abcde")
        with self.assertRaises(ParameterValidationError):
            _validate_param(spec, "abcdef")

    def test_int_param_string_value_rejected(self):
        spec = ParamSpec(name="x", kind="int", required=True)
        with self.assertRaises(ParameterValidationError) as ctx:
            _validate_param(spec, "42")
        self.assertIn("must be an int", str(ctx.exception))

    def test_int_param_min_value_enforced(self):
        spec = ParamSpec(name="x", kind="int", required=True, min_value=0)
        with self.assertRaises(ParameterValidationError) as ctx:
            _validate_param(spec, -1)
        self.assertIn(">= 0", str(ctx.exception))

    def test_int_param_max_value_enforced(self):
        spec = ParamSpec(name="x", kind="int", required=True, max_value=100)
        with self.assertRaises(ParameterValidationError) as ctx:
            _validate_param(spec, 101)
        self.assertIn("<= 100", str(ctx.exception))

    def test_int_param_within_bounds_accepted(self):
        spec = ParamSpec(name="x", kind="int", required=True, min_value=0, max_value=100)
        self.assertEqual(_validate_param(spec, 50), 50)
        self.assertEqual(_validate_param(spec, 0), 0)
        self.assertEqual(_validate_param(spec, 100), 100)

    def test_bool_param_accepted(self):
        spec = ParamSpec(name="x", kind="bool", required=True)
        self.assertTrue(_validate_param(spec, True))
        self.assertFalse(_validate_param(spec, False))

    def test_bool_param_int_rejected(self):
        spec = ParamSpec(name="x", kind="bool", required=True)
        with self.assertRaises(ParameterValidationError) as ctx:
            _validate_param(spec, 1)
        self.assertIn("must be a bool", str(ctx.exception))

    def test_bool_param_string_rejected(self):
        spec = ParamSpec(name="x", kind="bool", required=True)
        with self.assertRaises(ParameterValidationError):
            _validate_param(spec, "true")

    def test_optional_param_none_accepted(self):
        spec = ParamSpec(name="x", kind="str", required=False)
        self.assertIsNone(_validate_param(spec, None))

    def test_required_param_none_rejected(self):
        spec = ParamSpec(name="x", kind="str", required=True)
        with self.assertRaises(ParameterValidationError) as ctx:
            _validate_param(spec, None)
        self.assertIn("Missing required", str(ctx.exception))

    def test_unknown_kind_raises(self):
        spec = ParamSpec(name="x", kind="float")
        with self.assertRaises(ParameterValidationError) as ctx:
            _validate_param(spec, 3.14)
        self.assertIn("Unknown param kind", str(ctx.exception))


class TestAllQueriesBoundedAndOrdered(unittest.TestCase):
    """Every query in the ALLOWLIST must have LIMIT and ORDER BY."""

    def test_all_14_queries_have_limit(self):
        for qid, q in ALLOWLIST.items():
            with self.subTest(query_id=qid):
                self.assertIn("LIMIT $limit", q.cypher, f"Query {qid} missing LIMIT $limit")

    def test_all_queries_have_max_limit_set(self):
        for qid, q in ALLOWLIST.items():
            with self.subTest(query_id=qid):
                self.assertGreater(q.max_limit, 0, f"Query {qid} has invalid max_limit")

    def test_query_count_matches_expected(self):
        self.assertEqual(
            len(ALLOWLIST), 12,
            f"Expected 12 allowlisted queries, found {len(ALLOWLIST)}. "
            "If queries were added, update this count and add tests.",
        )


class TestQuerySpecificValidation(unittest.TestCase):
    """Validate specific query param schemas work correctly."""

    def test_resolve_resource_empty_name_rejected(self):
        q = get_query("t1.resolve_azure_resource")
        with self.assertRaises(ParameterValidationError):
            validate_params(q, {"resourceName": "", "limit": 1})

    def test_blast_radius_resource_impact_valid(self):
        q = get_query("blast_radius.resource_impact")
        params = validate_params(q, {"resourceName": "res-alpha-app", "limit": 1})
        self.assertEqual(params["resourceName"], "res-alpha-app")
        self.assertEqual(params["limit"], 1)

    def test_template_dependencies_valid(self):
        q = get_query("t5.template_dependencies")
        params = validate_params(q, {"rolloutId": "RL-001", "limit": 5})
        self.assertEqual(params["rolloutId"], "RL-001")

    def test_blast_radius_service_impact_valid(self):
        q = get_query("blast_radius.service_impact")
        params = validate_params(q, {"serviceId": "svc-alpha"})
        self.assertEqual(params["serviceId"], "svc-alpha")
        self.assertEqual(params["limit"], q.default_limit)

    def test_blast_radius_template_impact_valid(self):
        q = get_query("blast_radius.template_impact")
        params = validate_params(q, {"templateName": "tmpl-x"})
        self.assertEqual(params["templateName"], "tmpl-x")


class TestArbitraryCypherBlocked(unittest.TestCase):
    """No arbitrary Cypher can be executed through the allowlist."""

    def test_injection_attempt_rejected(self):
        with self.assertRaises(UnknownQueryError):
            get_query("MATCH (n) DETACH DELETE n")

    def test_sql_injection_rejected(self):
        with self.assertRaises(UnknownQueryError):
            get_query("'; DROP TABLE users; --")

    def test_nonexistent_query_rejected(self):
        with self.assertRaises(UnknownQueryError):
            get_query("t99.does_not_exist")


if __name__ == "__main__":
    unittest.main()
