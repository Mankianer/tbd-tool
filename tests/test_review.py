from tbd.core.review import Option, Review, ReviewItem, parse_decisions


def test_render_and_parse_roundtrip():
    review = Review()
    review.add(ReviewItem("person:kira", "Kira", options=[
        Option("create", "Neu anlegen"), Option("alias", "Alias von [[Bellis]]"), Option("ignore", "Ignorieren")]),
        occurrence="2026-06-12")
    text = review.render()
    assert "[[2026-06-12]]" in text
    assert parse_decisions(text) == []

    ticked = text.replace("- [ ] Alias von [[Bellis]]", "- [x] Alias von [[Bellis]]")
    [decision] = parse_decisions(ticked)
    assert (decision.item_id, decision.action, decision.target, decision.title) == \
        ("person:kira", "alias", "Bellis", "Kira")


def test_user_can_edit_alias_target():
    text = "### Kira\n%% id: person:kira %%\n- [x] Alias von [[Kira Muster]] %% action: alias %%\n"
    assert parse_decisions(text)[0].target == "Kira Muster"
