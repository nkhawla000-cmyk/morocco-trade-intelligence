# Guide de compréhension — Morocco Trade Intelligence

Ce guide explique le projet de bout en bout : ce qu'il fait, pourquoi chaque choix a été fait, et comment le présenter en entretien.

## 1. Le projet en 30 secondes

> « J'ai construit un pipeline de données qui collecte automatiquement les statistiques du commerce extérieur marocain auprès de l'API UN Comtrade, contrôle leur qualité, les organise en modèle en étoile avec dbt et DuckDB, puis calcule des indicateurs : balance commerciale, principaux partenaires, concentration des échanges (indice HHI) et écarts entre les déclarations du Maroc et celles de ses partenaires. Tout est testé automatiquement et s'exécute sur GitHub Actions. »

## 2. Le chemin des données

```
API UN Comtrade → fichiers JSON bruts → fichier bronze → staging dbt → modèle en étoile → tables d'analyse → exports Parquet/CSV
```

| Étape | Fichier | Ce qu'il faut retenir |
|---|---|---|
| Plan des appels | `src/mti/config.py` | 10 appels par année, 70 pour 2019–2025. Chaque appel est découpé pour rester sous la limite de 500 lignes de l'API gratuite. |
| Appel de l'API | `src/mti/comtrade.py` | Nouvelles tentatives en cas d'erreur temporaire (429, 5xx), pause entre les appels, contrôle de la réponse. |
| Extraction | `src/mti/extract.py` | Une réponse = un fichier JSON. Le lot est « tout ou rien » : si un appel échoue, l'ancien jeu de données reste intact. |
| Bronze | `src/mti/bronze.py` | Tous les enregistrements dans un seul fichier, avec des types fixes et des colonnes de traçabilité. |
| Transformation | `dbt/models/` | SQL versionné et testé : nettoyage, modèle en étoile, indicateurs. |
| Tests de données | `dbt/tests/` + fichiers `.yml` | Environ 40 contrôles exécutés à chaque construction. |
| Export | `src/mti/export.py` | Tables en Parquet (modèle en étoile) et en CSV (indicateurs), prêtes pour Power BI. |
| Orchestration | `run_pipeline.py` | Enchaîne les étapes et écrit un rapport d'exécution. |

## 3. Les données UN Comtrade

- **Reporter** : le pays qui déclare (ici surtout le Maroc, code 504).
- **Partner** : le pays avec lequel il échange. Le code 0 = « World », le total mondial.
- **Flow** : `X` = exportations, `M` = importations.
- **Code produit (HS)** : `TOTAL` = tous produits ; 2 chiffres = chapitre (87 = véhicules) ; 4 chiffres = position (8708 = parties de véhicules).
- **primaryValue** : valeur en dollars US. Les exportations sont généralement valorisées **FOB** (sans transport ni assurance), les importations **CIF** (avec transport et assurance).

**Les quatre jeux de données collectés :**

1. `products_world` : commerce du Maroc avec le monde par chapitre HS.
2. `partners_total` : commerce total du Maroc par pays partenaire.
3. `automotive_partners` : voitures (8703), parties de véhicules (8708) et fils et câbles isolés, dont les faisceaux de câblage automobile (8544), par pays partenaire.
4. `mirror_partners` : ce que 15 grands partenaires déclarent sur leur commerce avec le Maroc.

## 4. Pourquoi ces choix techniques

- **Garder les réponses brutes** : on peut toujours retraiter les données sans rappeler l'API, et prouver d'où vient chaque chiffre.
- **Un lot « tout ou rien »** : un rafraîchissement interrompu ne laisse jamais un mélange d'anciennes et de nouvelles données.
- **Rejeter une réponse de 500 lignes** : 500 est le maximum de l'API gratuite. Une réponse pleine signifie peut-être des données coupées ; mieux vaut échouer clairement que perdre des lignes en silence.
- **Modèle en étoile** : une table de faits (`fct_trade`) et des dimensions (pays, produit, flux, année). C'est la structure attendue par Power BI et la plus simple à interroger.
- **dbt** : chaque transformation est un fichier SQL versionné, documenté et testé, avec un graphe de dépendances.
- **DuckDB** : base analytique dans un simple fichier, sans serveur. Les modèles dbt pourront être portés sur PostgreSQL si besoin.

**Point d'attention :** la table de faits mélange des niveaux de produit (TOTAL, chapitres, positions). Il ne faut jamais les additionner entre eux. On filtre toujours d'abord sur `dim_product.product_level`.

## 5. Les contrôles de qualité

- **À l'extraction** : code HTTP, structure de la réponse, message d'erreur de l'API, pays ou année inattendus, réponse tronquée.
- **Tests dbt** :
  - clés uniques et non nulles ;
  - valeurs autorisées (X/M) ;
  - intégrité référentielle : chaque ligne de `fct_trade` pointe vers un pays, un produit, un flux et une année existants ;
  - pas de valeurs négatives ;
  - HHI entre 0 et 10 000 ;
  - pas de doublons contradictoires dans la source.
- **Rapprochement** : la somme des chapitres HS doit correspondre au total déclaré. Un écart de plus de 1 % déclenche un avertissement, pas un échec : c'est un signal à examiner.
- **Rapport** : `data/pipeline_report.json` indique, à chaque exécution, le nombre de lignes par jeu de données, les appels vides et le résultat des tests.

## 6. Les indicateurs

- **Balance commerciale** = exportations − importations.
- **Taux de couverture** = exportations ÷ importations.
- **Part d'un partenaire** = valeur avec ce partenaire ÷ total mondial.
- **Indice HHI** = 10 000 × somme des parts au carré.
  - Exemple : deux partenaires à 50 % donnent 10 000 × (0,5² + 0,5²) = 5 000.
  - Un seul partenaire donne 10 000 ; cent partenaires égaux donnent 100.
  - Seuils indicatifs : moins de 1 500 = faible, 1 500 à 2 500 = modérée, plus de 2 500 = élevée.
  - On exclut « World » et les zones non spécifiées pour que les parts somment à 1.
- **Statistiques miroirs** : on compare ce que le Maroc déclare exporter vers un pays avec ce que ce pays déclare importer du Maroc.
  - Un écart de quelques pourcents est normal : CIF contre FOB, décalages de date, classements différents.
  - Au-delà de 20 %, la ligne est marquée « à examiner » (`needs_review`). Ce n'est pas une erreur prouvée.

## 7. Lancer le projet

- **Sur GitHub** : onglet *Actions* → *Refresh data* → *Run workflow*. Les tables sont mises à jour dans `data/marts`.
- **Sur votre ordinateur** (Windows) :

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest -q
python run_pipeline.py --offline   # sans Internet, données synthétiques
python run_pipeline.py             # vraies données
```

Le mode `--offline` utilise des réponses inventées (`src/mti/fake_api.py`). Il sert uniquement aux tests : ces chiffres ne doivent jamais être présentés comme des résultats.

## 8. Limites à connaître

- Données annuelles uniquement, en dollars courants (pas corrigées de l'inflation).
- Les trois positions HS automobiles sont un indicateur, pas une définition complète du secteur.
- L'API gratuite limite chaque appel à 500 lignes, ce qui impose un découpage fin.
- Les données récentes (dernière année) peuvent être incomplètes ou révisées par la suite.

## 9. Questions probables en entretien

**Pourquoi un modèle en étoile ?**
Pour séparer les mesures (valeurs échangées) des axes d'analyse (pays, produit, flux, année). Les requêtes et les rapports Power BI sont plus simples et plus rapides.

**Que se passe-t-il si l'API tombe en panne pendant l'extraction ?**
Le client réessaie avec un délai croissant. Si l'échec persiste, le lot entier est abandonné et l'ancien jeu de données reste en place.

**Comment savez-vous que vos données sont fiables ?**
Par les contrôles à l'extraction, les tests dbt à chaque construction, le rapprochement chapitres/total et le rapport d'exécution publié.

**Pourquoi les déclarations du Maroc et de ses partenaires ne concordent-elles pas ?**
Importations en CIF contre exportations en FOB, décalages de date, différences de classement ou de pays d'origine. Des écarts importants signalent des points à vérifier.

**Que signifie un HHI de 2 000 ?**
Une concentration modérée. C'est l'équivalent de cinq partenaires de même poids (10 000 ÷ 5 = 2 000).

**Pourquoi DuckDB et pas PostgreSQL ?**
DuckDB est une base analytique sans serveur, idéale pour un projet portable et des tests en intégration continue. dbt permet de passer à PostgreSQL en changeant seulement le profil de connexion.

**Comment le pipeline est-il automatisé ?**
GitHub Actions lance les tests à chaque modification du code, et le rafraîchissement des données chaque mois. L'étape suivante est l'orchestration avec Airflow.

## 10. Prochaines étapes

1. **v0.2** : orchestration Airflow dans Docker. Un DAG avec une tâche par étape, des relances et un suivi des exécutions.
2. **v0.3** : rapport Power BI sur le modèle en étoile exporté.
3. **v0.4** : détection d'anomalies sur les flux et segmentation des partenaires.
