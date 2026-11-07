# Guide de compréhension — Morocco Trade Intelligence

Ce guide explique le projet de bout en bout : ce qu'il fait, pourquoi chaque choix a été fait, et comment le présenter en entretien.

## 1. Le projet en 30 secondes

> « J'ai construit un pipeline de données qui collecte automatiquement les statistiques du commerce extérieur marocain auprès de l'API UN Comtrade, contrôle leur qualité et les organise en modèle en étoile avec dbt et DuckDB. Il calcule ensuite des indicateurs (balance commerciale, principaux partenaires, concentration HHI, statistiques miroirs), détecte les variations anormales et segmente les pays partenaires avec un k-means. Le tout est orchestré par Airflow, testé automatiquement sur GitHub Actions et restitué dans un rapport Power BI de six pages. »

## 2. Le chemin des données

```
API UN Comtrade → JSON bruts → bronze → staging dbt → modèle en étoile → tables d'analyse et segmentation
→ exports Parquet/CSV → rapport Power BI
```

| Étape | Fichier | Ce qu'il faut retenir |
|---|---|---|
| Plan des appels | `src/mti/config.py` | 10 appels par année, 70 pour 2019–2025. Chaque appel est découpé pour rester sous la limite de 500 lignes de l'API gratuite. |
| Appel de l'API | `src/mti/comtrade.py` | Nouvelles tentatives en cas d'erreur temporaire (429, 5xx), pause entre les appels, contrôle de la réponse. |
| Extraction | `src/mti/extract.py` | Une réponse = un fichier JSON. Le lot est « tout ou rien » : si un appel échoue, l'ancien jeu de données reste intact. |
| Bronze | `src/mti/bronze.py` | Tous les enregistrements dans un seul fichier, avec des types fixes et des colonnes de traçabilité. |
| Transformation | `dbt/models/` | SQL versionné et testé : nettoyage, modèle en étoile, indicateurs. |
| Tests de données | `dbt/tests/` + fichiers `.yml` | Plus de 45 contrôles exécutés à chaque construction. |
| Anomalies | `dbt/models/marts/analytics/mart_flow_anomalies.sql` | Score z robuste de la variation annuelle de chaque partenaire. |
| Segmentation | `src/mti/segmentation.py` | k-means sur 4 indicateurs par partenaire, avec scikit-learn. |
| Export | `src/mti/export.py` | Tables en Parquet (modèle en étoile) et en CSV (indicateurs), prêtes pour Power BI. |
| Orchestration | `run_pipeline.py`, `airflow/dags/mti_pipeline.py` | Six étapes nommées, lançables seules ; Airflow les enchaîne, une tâche par étape. |
| Rapport | `powerbi/` | Projet Power BI généré par `tools/build_powerbi.py`, lu depuis GitHub. |

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

## 8. Une découverte de qualité des données : une rupture possible en 2024

Au premier lancement sur les vraies données, les exportations du Maroc passent de 42,5 milliards de dollars en 2023 à 80,6 milliards en 2024. Les importations passent de 70,6 à 98,0 milliards.

**Ce qui a été vérifié :**
- **L'API elle-même** renvoie 80,6 milliards de dollars pour 2024, sur une seule ligne de total. Le pipeline n'a donc ni doublé ni mal agrégé les données.
- **Les chiffres nationaux** (Office des Changes) donnent 456,3 milliards de dirhams d'exportations en 2024, soit environ 46 milliards de dollars, et 761,3 milliards de dirhams d'importations, soit environ 76 milliards de dollars.
- **Les statistiques miroirs** vont dans le même sens : 25 comparaisons sur 28 sont « à examiner » en 2024, contre environ la moitié les années précédentes.

**Ce que fait le pipeline :** il garde les valeurs de la source sans les modifier, signale la rupture (colonne `possible_series_break` et avertissement dbt) et la documente.

**Conséquence pour l'analyse :** ne pas comparer 2024–2025 avec les années précédentes sans précaution. Les parts des partenaires au sein d'une même année restent exploitables.

**Ce qu'on ne sait pas encore :** l'origine de l'écart. Il peut venir d'un changement de périmètre (zones franches, trafic de perfectionnement), de valorisation ou de méthode de compilation. On parle donc de « rupture possible », pas de rupture démontrée.

**En entretien, c'est votre meilleur exemple :** un contrôle automatique a repéré un écart important dans une source officielle. Vous l'avez comparé à une seconde source (l'Office des Changes, qui n'a rien « confirmé » : vous avez comparé ses chiffres publiés), puis documenté sans corriger les données à la main et sans conclure au-delà des preuves.

## 9. Détection d'anomalies

**Question :** quels partenaires ont une variation annuelle anormale par rapport aux autres partenaires la même année ?

1. Pour chaque partenaire et chaque flux, on calcule la variation en logarithme : ln(valeur de l'année / valeur de l'année précédente). Le logarithme rend comparables une hausse et une baisse.
2. On calcule, pour la même année et le même flux, la **médiane** des variations de tous les partenaires et leur **écart absolu médian** (MAD).
3. **Score z robuste** = (variation − médiane) / (1,4826 × MAD). Le facteur 1,4826 rend le MAD comparable à un écart-type.
4. Au-delà de 3,5 en valeur absolue, la variation est signalée. Seuls les partenaires d'au moins 50 millions de dollars l'année précédente sont évalués : les petits flux varient beaucoup sans raison significative.

**Pourquoi la médiane plutôt que la moyenne ?** Parce qu'elle n'est pas tirée par les valeurs extrêmes qu'on cherche justement à détecter.

**Pourquoi la rupture de 2024 n'est-elle pas signalée partout ?** Parce que chaque partenaire est comparé aux autres partenaires de la même année. Si tout le monde monte de 90 %, la médiane monte aussi, et seuls les écarts à ce mouvement général ressortent.

## 10. Segmentation des partenaires (k-means)

**Question :** quels groupes de pays partenaires se ressemblent ?

Quatre indicateurs par partenaire, calculés sur 2019–2023, avant la rupture de série :
- **taille** des échanges : logarithme de la moyenne exportations + importations ;
- **part des exportations** : exportations ÷ échanges ; proche de 1 = débouché, proche de 0 = fournisseur ;
- **croissance** : taux de croissance annuel moyen des échanges ;
- **part automobile** : voitures, pièces et câblage dans les exportations vers ce pays.

**Étapes :** les indicateurs sont standardisés (moyenne 0, écart-type 1) pour qu'aucun ne domine. On teste k de 3 à 6 et on garde le k au meilleur **score de silhouette**, qui mesure si chaque pays est plus proche de son groupe que des autres. Chaque segment reçoit ensuite un nom tiré de son profil médian (par exemple « Grands partenaires — échanges équilibrés, orientés automobile »).

**Limites :** un k-means trouve toujours des groupes, même faibles. Le score de silhouette, publié dans le rapport d'exécution, indique leur netteté. La segmentation sert à décrire, pas à prédire.

## 11. Orchestration avec Airflow

- **DAG** `morocco_trade_intelligence` : six tâches (`extract → bronze → dbt → segment → export → report`), lancé le 7 de chaque mois.
- **Chaque tâche** exécute `run_pipeline.py --steps <étape>` : on peut relancer une seule étape à la main, avec la même commande.
- **Relances :** seule l'extraction est relancée automatiquement (3 fois, toutes les 10 minutes), car c'est la seule étape qui dépend d'un service extérieur.
- **Docker :** l'image Airflow contient un environnement Python séparé pour le projet. dbt et les bibliothèques de données n'entrent donc pas en conflit avec celles d'Airflow.
- **Test automatique :** à chaque modification du pipeline, GitHub Actions construit l'image et exécute le DAG complet sur données synthétiques.

**Lancer Airflow sur votre Dell :** installez Docker Desktop, puis dans le dossier du projet :

```bash
docker compose up --build
docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt
```

Ouvrez http://localhost:8080 avec l'utilisateur `admin` et ce mot de passe, puis activez et lancez le DAG.

## 12. Le rapport Power BI

Six pages : vue d'ensemble, partenaires, produits, automobile et concentration, qualité des données, segmentation. Le mode d'emploi est dans `powerbi/README.md`.

- Le rapport lit les tables publiées sur GitHub : une actualisation charge les données du dernier rafraîchissement mensuel.
- Le modèle relie la table de faits à quatre dimensions (modèle en étoile). Les tables d'analyse sont reliées à la dimension année quand une page les filtre par année.
- Les mesures DAX sont dans `powerbi/mesures.dax`. Exemple : `Année affichée` renvoie l'année choisie dans le segment, ou la dernière année disponible si rien n'est choisi.

## 13. Limites à connaître

- Données annuelles uniquement, en dollars courants (pas corrigées de l'inflation).
- Les trois positions HS automobiles sont un indicateur, pas une définition complète du secteur.
- L'API gratuite limite chaque appel à 500 lignes, ce qui impose un découpage fin.
- Les données récentes (dernière année) peuvent être incomplètes ou révisées par la suite.

## 14. Questions probables en entretien

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
GitHub Actions lance les tests à chaque modification du code et rafraîchit les données chaque mois. Airflow orchestre les mêmes étapes en local, une tâche par étape, avec des relances sur l'extraction.

**Pourquoi un score z robuste pour les anomalies ?**
La moyenne et l'écart-type sont déformés par les valeurs extrêmes qu'on cherche à repérer. La médiane et le MAD ne le sont pas.

**Comment avez-vous choisi le nombre de segments ?**
Avec le score de silhouette, en testant k de 3 à 6. Les indicateurs sont standardisés avant le k-means, sinon la taille des échanges dominerait.

**Pourquoi la segmentation s'arrête-t-elle en 2023 ?**
À cause de la rupture de série de 2024 : les valeurs déclarées par le Maroc changent de niveau, ce qui fausserait la croissance.

## 15. Pistes d'amélioration

1. Charger l'entrepôt dans PostgreSQL en plus de DuckDB (profil dbt supplémentaire).
2. Passer aux données mensuelles pour suivre la conjoncture.
3. Publier le rapport Power BI dans le service Power BI, avec actualisation planifiée.
