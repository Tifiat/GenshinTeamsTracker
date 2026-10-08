import unittest

from run_workspace.gcsim.rotation_editor.model import Document, Span, node
from run_workspace.gcsim.rotation_editor.options import (
    ActionOption,
    CharacterOptions,
    EngineIdentity,
    ParameterOption,
)
from run_workspace.gcsim.rotation_editor.syntax import Dialect, parse
from run_workspace.gcsim.rotation_editor.validation import validate_actions, validate_setup


IDENTITY = EngineIdentity("test-engine", "source-fingerprint")
DIALECT = Dialect({"watergirl": "furina", "furina": "furina", "chasca": "chasca"})


def document(source):
    parsed = parse(source, DIALECT)
    assert parsed.syntax_complete, parsed.diagnostics
    return parsed


def codes(diagnostics):
    return [diagnostic.code for diagnostic in diagnostics]


class RotationValidationTests(unittest.TestCase):
    def test_options_types_and_unknown_key(self):
        good = document("options iteration=100 workers=2 duration=90.5 debug=true mode=legacy frame_defaults=human swap_delay=3;")
        self.assertEqual(validate_setup(good), ())
        bad = document("options iteration=1.5 duration=foo hitlag=1 frame_defaults=machine er_calc=true;")
        found = codes(validate_setup(bad))
        self.assertIn("rotation.setup.value_type", found)
        self.assertIn("rotation.setup.frame_defaults", found)
        self.assertIn("rotation.setup.option_unknown", found)
        self.assertEqual(found.count("rotation.setup.value_type"), 3)
        signed = document("options iteration=-2 duration=-1.5;")
        self.assertEqual(codes(validate_setup(signed)).count("rotation.setup.value_type"), 2)

    def test_character_details_and_skipped_unknown_field(self):
        good = document("furina char lvl=80/90 +params=[story_buff=1+2] cons=6 talent=8,9,10;")
        self.assertEqual(validate_setup(good), ())
        bool_param = document("furina char lvl=80/90 +params=[flag=true];")
        self.assertEqual(validate_setup(bool_param), ())
        skipped = document("furina char mystery=7;")
        result = validate_setup(skipped)
        self.assertEqual(codes(result), ["rotation.setup.character_field_skipped"])
        self.assertEqual(result[0].severity, "warning")
        plus_unknown = document("furina char +mystery=7;")
        self.assertIn("rotation.setup.character_plus_unknown", codes(validate_setup(plus_unknown)))
        bad = document("furina char lvl=90/80 +params=[bonus=foo] cons=1.5 talent=1,2,3.5;")
        self.assertIn("rotation.setup.level_pair", codes(validate_setup(bad)))
        self.assertIn("rotation.setup.params_type", codes(validate_setup(bad)))

    def test_add_weapon_set_and_stats(self):
        good = document('furina add weapon="test sword" lvl=80/90 +params=[boost=2] refine=1; '
                        'furina add set="test set" count=4; '
                        'furina add stats hp=100+20 atk=300 label=base; '
                        'furina add stats random rarity=5 sand=hp% goblet=hydro% circlet=cr;')
        self.assertEqual(validate_setup(good), ())
        missing = document('furina add weapon="test sword" lvl=80/90; furina add set="test set";')
        result = validate_setup(missing)
        self.assertIn("rotation.setup.weapon_required", codes(result))
        self.assertIn("rotation.setup.set_count_default", codes(result))
        self.assertEqual(next(d.severity for d in result if d.code == "rotation.setup.set_count_default"), "warning")
        mixed_random = document("furina add stats hp=1 random rarity=5 sand=hp%;")
        self.assertEqual(codes(validate_setup(mixed_random)), ["rotation.setup.random_after_stats"])

    def test_target_order_types_and_numeric_constants(self):
        good = document("target lvl=90 type=slime[hp_mult=2,particles=1] pos=1+2,3*4 resist=.1+.2 hp=1000 particle_element=pyro;")
        self.assertEqual(validate_setup(good), ())
        late = document("target type=slime hp=1000 lvl=90;")
        self.assertIn("rotation.setup.target_level_before_type", codes(validate_setup(late)))
        bad = document("target lvl=0 pos=variable,2 hp=1+2 unknown=4;")
        found = codes(validate_setup(bad))
        self.assertIn("rotation.setup.target_level", found)
        self.assertIn("rotation.setup.value_type", found)
        self.assertIn("rotation.setup.target_field_unknown", found)
        param_expression = document("target lvl=90 type=slime[hp_mult=1+2];")
        self.assertIn("rotation.setup.params_type", codes(validate_setup(param_expression)))
        dynamic = document("target lvl=90 pos=variable,.furina.hp resist=variable;")
        self.assertEqual(codes(validate_setup(dynamic)).count("rotation.setup.value_type"), 2)
        signed = document("target lvl=90 hp=-1 resist=-.1;")
        self.assertEqual(codes(validate_setup(signed)), ["rotation.setup.value_type"])
        strict = document("target lvl=90 radius=1+2 hp=1+2 particle_threshold=1+2 particle_drop_count=1+2;")
        self.assertEqual(codes(validate_setup(strict)).count("rotation.setup.value_type"), 4)
        folded = document("target lvl=90 freeze_resist=1+2 pyro=1+2;")
        self.assertEqual(validate_setup(folded), ())
        zero_divisor = document("target lvl=90 pos=1/(2-2),0;")
        self.assertIn("rotation.setup.value_type", codes(validate_setup(zero_divisor)))
        truncated_zero = document("target lvl=90 resist=1/(1/2);")
        self.assertIn("rotation.setup.value_type", codes(validate_setup(truncated_zero)))
        truncated_nonzero = document("target lvl=90 resist=1/(3/2);")
        self.assertEqual(validate_setup(truncated_nonzero), ())
        wrapped_zero = document("target lvl=90 resist=1/(9223372036854775807+1+9223372036854775807+1);")
        self.assertIn("rotation.setup.value_type", codes(validate_setup(wrapped_zero)))
        comparisons = document("target lvl=90 resist=1<2 freeze_resist=!(1<2) pos=1&&0,1<>2;")
        self.assertEqual(validate_setup(comparisons), ())
        self.assertIn("rotation.setup.target_field_unknown", codes(validate_setup(document("target +hp=100;"))))

    def test_energy_and_hurt_envelopes_and_rotation_shell(self):
        self.assertEqual(validate_setup(document("chasca skill;")), ())
        good = document("energy once interval=300 amount=1; energy every interval=300,600 amount=2; "
                        "hurt once interval=300 amount=1,300 element=physical; "
                        "hurt every interval=480,720 amount=1,300 element=pyro;")
        self.assertEqual(validate_setup(good), ())
        bad = document("energy every interval=300 amount=1; hurt once amount=1 element=foo;")
        self.assertGreaterEqual(codes(validate_setup(bad)).count("rotation.setup.value_type"), 3)

    def test_event_frequency_requires_initial_selector(self):
        def setting(key, *values):
            return node("setting", key=node("name", value=key), values=tuple(node("number", value=str(value)) for value in values), plus=False)
        def event(*entries, selector=None):
            setup = node("setup", actor=None, directive=node("name", value="energy"),
                         selector=node("name", value=selector) if selector else None, entries=entries)
            return Document("", node("document", items=(setup,)), DIALECT)
        self.assertEqual(validate_setup(event()), ())
        self.assertEqual(validate_setup(event(setting("interval", 300, 600), setting("amount", 1), selector="every")), ())
        self.assertEqual(validate_setup(event(setting("interval", 300), selector="once")), ())
        self.assertIn("rotation.setup.event_selector", codes(validate_setup(event(setting("interval", 300, 600)))))
        late_flag = validate_setup(event(setting("interval", 300, 600), setting("every"), selector="every"))
        self.assertIn("rotation.setup.event_field_unknown", codes(late_flag))

    def test_action_alias_invalid_note_params_and_identity(self):
        parsed = document("watergirl skill[hold=1],burst[wrong=1],attack;")
        options = CharacterOptions(
            "furina", IDENTITY,
            (ActionOption("skill", False, "Only after setup"), ActionOption("burst", True), ActionOption("attack", False)),
            (ParameterOption("skill", "hold", "0 or 1"), ParameterOption("burst", "known", "value")),
            (), "local",
        )
        result = validate_actions(parsed, {"furina": options}, expected_identity=IDENTITY)
        self.assertIn("rotation.action.note", codes(result))
        self.assertIn("rotation.action.invalid", codes(result))
        self.assertIn("rotation.action.param_invalid", codes(result))
        self.assertNotIn("rotation.action.options_unavailable", codes(result))
        self.assertTrue(all(isinstance(item.span, Span) for item in result))
        stale = validate_actions(parsed, {"furina": options}, expected_identity=EngineIdentity("other", "other"))
        self.assertIn("rotation.action.options_stale", codes(stale))

    def test_action_missing_metadata_and_empty_param_table(self):
        parsed = document("chasca skill[hold=1];")
        soft = validate_actions(parsed, {})
        hard = validate_actions(parsed, {}, require_options=True)
        self.assertEqual(soft[0].severity, "warning")
        self.assertEqual(hard[0].severity, "error")
        options = CharacterOptions("chasca", IDENTITY, (ActionOption("skill", False),), (), (), "local")
        result = validate_actions(parsed, {"chasca": options})
        self.assertIn("rotation.action.param_undocumented", codes(result))
        self.assertNotIn("rotation.action.param_invalid", codes(result))

    def test_custom_execute_action_handler_skips_metadata_combat_checks(self):
        parsed = document("chasca skill[hold=1]; execute_action = fn(){return 1;};")
        options = CharacterOptions("chasca", IDENTITY, (ActionOption("skill", True),), (), (), "local")
        result = validate_actions(parsed, {"chasca": options}, expected_identity=IDENTITY, require_options=True)
        self.assertEqual(codes(result), ["rotation.action.custom_handler"])
        self.assertEqual(result[0].severity, "warning")


if __name__ == "__main__":
    unittest.main()
