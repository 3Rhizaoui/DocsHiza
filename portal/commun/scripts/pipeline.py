from __future__ import annotations

"""
Pipeline logique du Portal GIL.

Le point d'entrée opérationnel actuel est :

    jira/Importer_JIRA.cmd

Il réalise l'extraction JIRA puis appelle :

    portal/commun/scripts/publier_portal.py

Ce module matérialise l'architecture cible.
Il ne doit pas rappeler Importer_JIRA.cmd afin d'éviter
une orchestration imbriquée.
"""

PIPELINE_STEPS = (
    "Extraction JIRA",
    "Contrôles métier",
    "Normalisation",
    "Consolidation",
    "Publication Portal",
)


def describe() -> None:
    print("GIL PORTAL - PIPELINE")
    for index, step in enumerate(PIPELINE_STEPS, 1):
        print(f"[{index}/{len(PIPELINE_STEPS)}] {step}")


if __name__ == "__main__":
    describe()
