from ui.key_input import Debouncer


def test_debouncer_rejects_events_inside_interval():
    debouncer = Debouncer(interval_seconds=0.25)

    assert debouncer.accept(10.0)
    assert not debouncer.accept(10.1)
    assert debouncer.accept(10.25)
