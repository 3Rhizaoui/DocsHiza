# Runbook BNP — Tests Standalone GIL

## Objectif

Ce document décrit les commandes à exécuter sur le PC BNP pour valider la chaîne **Tests Standalone GIL** sans échanger de fichiers entre le PC BNP et le PC DEV.

Principe :
- développement et commits sur le PC DEV ;
- `git pull` puis exécution réelle sur le PC BNP ;
- diagnostic par lecture à l’écran / captures uniquement ;
- aucun fichier runtime, log, cookie, profil SSO ou secret ne doit être committé.

## 1. Mise à jour du dépôt sur le PC BNP

Depuis la racine du dépôt :

```bash
git pull origin GIL-General
git log -3 --oneline
git status --short
```

## 2. Vérification syntaxique du pipeline

```bash
python -m py_compile   portal/commun/scripts/pipeline.py
```

Puis vérifier les étapes :

```bash
python - <<'PY'
from pathlib import Path
import ast

p = Path("portal/commun/scripts/pipeline.py")
tree = ast.parse(p.read_text(encoding="utf-8"))

for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        if any(
            isinstance(t, ast.Name) and t.id == "steps"
            for t in node.targets
        ):
            print("TOTAL =", len(node.value.elts))
            for i, step in enumerate(node.value.elts, 1):
                print(f"{i:02d}.", ast.literal_eval(step.elts[0]))
PY
```

La publication Portal doit toujours rester la dernière étape.

## 3. Lancement du Portal

Ouvrir :

```text
http://127.0.0.1:8765/
```

Puis la page Standalone :

```text
http://127.0.0.1:8765/qualite/standalone/index.html
```

## 4. Rafraîchissement global

Depuis la Home, cliquer sur **Rafraîchir les données du projet**.

### JIRA principal
Se connecter si nécessaire et suivre l’invite.

### JIRA Standalone
Le script doit extraire les Epics dont le titre contient :

```text
[FEATURE GIL]
```

Contrôler :

```text
Capabilities : <nombre>
Issues enfants : <nombre>
```

Si `Issues enfants = 0` alors que les Epics contiennent des tâches, conserver une capture.

## 5. Connexion Octane SSO

Lors de l’ouverture d’Octane :
- utiliser l’adresse professionnelle autorisée sur le poste BNP ;
- terminer complètement l’authentification ;
- attendre le chargement du workspace ;
- revenir dans la console et appuyer sur Entrée.

Paramètres attendus :

```text
Base URL     : https://almoctane-eur.saas.microfocus.com
Shared Space : 489001
Workspace    : 104001
```

Ne jamais committer :
- identifiant personnel ;
- mot de passe ;
- cookie ;
- token ;
- profil Chrome/Edge SSO.

## 6. Diagnostic CDP Octane

Si le navigateur SSO ne répond pas :

```bash
curl http://127.0.0.1:9232/json/version
```

Puis :

```bash
curl http://127.0.0.1:9232/json/list
```

Attendu : `/json/list` contient un onglet dont l’URL commence par :

```text
https://almoctane-eur.saas.microfocus.com/
```

Si seule une page `login.saas.microfocus.com` apparaît, l’authentification n’est pas terminée.

## 7. Diagnostic de la normalisation Octane

Si le pipeline échoue sur `Normalisation Octane Standalone`, ne pas relancer tout le pipeline.

```bash
python   portal/commun/scripts/qualite/standalone/normalisation/normaliser_octane.py
```

Puis :

```bash
ls -la   portal/commun/data/standalone/octane/
```

Et :

```bash
python - <<'PY'
from pathlib import Path

p = Path(
    "portal/commun/data/standalone/octane/"
    "qualifications_brut.json"
)

print("Existe :", p.exists())

if p.exists():
    print("Taille :", p.stat().st_size)
PY
```

Interprétation :
- `Existe : False` → l’extraction Octane n’a pas produit le fichier attendu ;
- `Existe : True` → vérifier le format du JSON ou `normaliser_octane.py`.

Ne pas transférer le JSON runtime hors du poste BNP.

## 8. Cas de référence Octane — Exchange layer

```text
Capability Octane : 770019 — GIL - Exchange layer
Test Suite        : 1118086 — TS-GIL - Exchange layer
Suite Run         : 901502  — TS-GIL - Exchange layer
```

Exécutions de référence :

```text
901503 — EventStream Kafka                    — Réussi
901504 — Transfert de fichier                 — Échec
901505 — Réception / Envoi de flux            — Réussi
901506 — Routage migration grands remettants  — Échec
901507 — Alimentation des assets groupe       — Réussi
901508 — Protocoles d’échange REST API        — Réussi
```

Résultat de référence :

```text
Exécutions : 6
PASS       : 4
FAIL       : 2
tousPass   : False
```

Il faut distinguer :

```text
Test Suite
Suite Run
Test Run
```

## 9. Contrat Ready for Use

Clé de rapprochement :

```text
Capability + Version/Release + Environnement
```

Une Capability ne peut être `Ready for Use` que si :
- JIRA : Capability trouvée, version/release correcte, environnement correct, tâches au statut attendu ;
- Octane : même Capability, même release, même environnement, Test Suite trouvée, exécutions correspondantes trouvées, résultats conformes, date disponible, preuves disponibles lorsque prévues.

Ne pas faire de rapprochement uniquement sur le titre.

## 10. Vérification de la page Standalone

Après génération correcte de :

```text
portal/commun/data/standalone/payload_standalone.json
```

ouvrir :

```text
http://127.0.0.1:8765/qualite/standalone/index.html
```

La page ne doit plus afficher :

```text
Payload Standalone indisponible : HTTP 404
```

## 11. Logs utiles

Pipeline :

```bash
tail -f   portal/logs/pipeline/pipeline_$(date +%F).log
```

Erreurs :

```bash
tail -f   portal/logs/errors/errors_$(date +%F).log
```

Ne pas committer les logs runtime.

## 12. Informations à relever après un test BNP

Relever uniquement :
1. numéro de l’étape en échec ;
2. nom de l’étape ;
3. code retour ;
4. message d’erreur exact ;
5. existence et taille du fichier attendu ;
6. capture d’écran si nécessaire.

Aucun export de données métier n’est nécessaire pour le diagnostic initial.
