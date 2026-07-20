from refengine.services.author_parser import parse_authors


def test_parses_affiliation_markers_and_conjunctions() -> None:
    raw = "Sherif Hamdy1, Aurélie Charrier1, Laurence Le Corre1 and David Rousseau2,4*"

    authors = parse_authors(raw)

    assert [author.family_name for author in authors] == [
        "Hamdy",
        "Charrier",
        "Le Corre",
        "Rousseau",
    ]


def test_keeps_portuguese_particle_with_given_names() -> None:
    authors = parse_authors("Edmar Soares de Vasconcelos; André Dantas de Medeiros")

    assert [(author.family_name, author.given_names) for author in authors] == [
        ("Vasconcelos", "Edmar Soares de"),
        ("Medeiros", "André Dantas de"),
    ]


def test_review_author_accepts_abnt_entry_form() -> None:
    from refengine.services.author_parser import parse_review_authors

    authors = parse_review_authors("MARCOS FILHO, J.; LO GIUDICE, Agata")

    assert authors[0].family_name == "MARCOS FILHO"
    assert authors[0].given_names == "J."
    assert authors[1].family_name == "LO GIUDICE"
