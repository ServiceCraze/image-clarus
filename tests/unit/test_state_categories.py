from image_clarus.state.categories import CategoryState
from image_clarus.state.storage import MemoryStorage


def test_memory_union_preserves_exact_complete_paths_and_snapshot_copy():
    state = CategoryState(MemoryStorage())
    state.add_categories(
        ["Animals/Birds/Owl", "Animals", "animals", "Animals/Birds/Owl"]
    )
    snapshot = state.snapshot_categories()
    assert snapshot == ["Animals", "Animals/Birds/Owl", "animals"]
    snapshot.clear()
    assert len(state.snapshot_categories()) == 3
    state.close()
    assert CategoryState(MemoryStorage()).snapshot_categories() == []
