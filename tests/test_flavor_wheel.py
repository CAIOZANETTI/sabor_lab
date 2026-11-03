"""Roda de aromas (gráfico radial em Plotly)."""

from __future__ import annotations

import pytest

from flavorlab.flavor_wheel import NOTE, NOTE_HTML, wheel_data, wheel_figure


def test_wheel_data_sectors_and_partners(tiny_db):
    d = wheel_data(tiny_db, "fg:1", n_descriptors=3, n_partners=6, min_molecules=1)
    assert d.n_molecules == 5                                     # cinnamon {1,2,3,4} + fdb:10 {1,9}
    assert sum(s.width_deg for s in d.sectors) == pytest.approx(360.0)
    assert [s.descriptor for s in d.sectors][0] == "sweet"         # mais frequente primeiro
    ids = [p.ingredient_id for p in d.partners]
    assert "fg:1" not in ids and "fdb:10" not in ids                # o próprio destaque não aparece
    assert "fg:3" not in ids                                        # variante "ground cinnamon" excluída
    assert len(ids) == len(set(ids))                                # cada ingrediente em um único setor
    clove = next(p for p in d.partners if p.ingredient_id == "fg:2")
    assert clove.npmi == pytest.approx(0.4)
    assert 0 < clove.jaccard <= 1 and clove.overall_jaccard == pytest.approx(0.5)
    for p in d.partners:
        sec = next(s for s in d.sectors if s.descriptor == p.descriptor)
        assert sec.start_deg <= p.theta_deg <= sec.start_deg + sec.width_deg


def test_missing_npmi_is_not_incompatibility(tiny_db):
    d = wheel_data(tiny_db, "fg:1", n_descriptors=3, n_partners=6, min_molecules=1)
    saffron = next(p for p in d.partners if p.ingredient_id == "fdb:11")
    assert saffron.npmi is None                                     # sem dado ≠ 0 ≠ incompatível
    assert "Nenhuma métrica mede gosto ou preferência" in NOTE
    assert "não percepção" in NOTE_HTML


def test_wheel_figure_is_deterministic_and_labelled(tiny_db):
    d = wheel_data(tiny_db, "fg:1", n_descriptors=3, n_partners=6, min_molecules=1)
    f1, f2 = wheel_figure(d), wheel_figure(wheel_data(tiny_db, "fg:1", n_descriptors=3, n_partners=6,
                                                     min_molecules=1))
    assert f1.to_json() == f2.to_json()
    kinds = [t.type for t in f1.data]
    assert kinds == ["barpolar", "barpolar", "scatterpolar", "scatterpolar"]
    ring, bars = f1.data[0], f1.data[1]
    assert len(ring.theta) == len(d.sectors) and len(bars.theta) == len(d.partners)
    assert all(0 < r <= 1.0 for r in bars.r)
    texts = " ".join(a.text for a in f1.layout.annotations)
    assert "Nenhuma métrica mede gosto" in texts


def test_unknown_ingredient_raises(tiny_db):
    with pytest.raises(ValueError):
        wheel_data(tiny_db, "ingrediente que não existe", min_molecules=1)
