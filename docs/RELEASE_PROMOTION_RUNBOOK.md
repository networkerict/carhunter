# Legacy Document

This document is preserved for historical reference.
Canonical, actively maintained documentation now lives in the new docs structure.
Start at [docs/README.md](README.md) for current operational and architecture guidance.

---

# AutoHunter Release Promotion Runbook

## Doel

Dit document beschrijft de standaardprocedure om een AutoHunter
development versie naar productie te brengen en daarna een nieuwe
development omgeving te maken.

------------------------------------------------------------------------

# Release proces

## 1. Development Freeze

Controle:

``` bash
git status
```

Maak een stabiele tag:

``` bash
git tag vX.Y-dev-stable
```

Test:

-   pipeline
-   scoring
-   dashboard
-   Telegram
-   database

------------------------------------------------------------------------

## 2. Productie directory maken

Voorbeeld:

``` bash
cp -a v2.8-dev v2.8
```

Controle:

``` bash
ls -la /opt/carhunter
```

------------------------------------------------------------------------

## 3. Database controleren

Een release bevat code en database.

Controle:

``` bash
sqlite3 carhunter.db "PRAGMA table_info(cars);"
```

Controleer:

-   nieuwe kolommen
-   indexen
-   bestaande data

------------------------------------------------------------------------

## 4. Versienummers aanpassen

Controleer:

-   VERSION
-   config.py
-   Python headers
-   templates
-   documentatie

Zoeken:

``` bash
grep -R "vX.Y"
```

------------------------------------------------------------------------

## 5. Productie symlink

Productie gebruikt:

    /opt/carhunter/current

Activeren:

``` bash
ln -sfn /opt/carhunter/vX.Y current
```

------------------------------------------------------------------------

## 6. Services aanpassen

Controleer:

``` bash
systemctl cat autohunter-web.service
systemctl cat autohunter-pipeline.service
```

Productie wijst naar:

    /opt/carhunter/current

------------------------------------------------------------------------

## 7. Poorten

Productie:

    5000

Development:

    5001

------------------------------------------------------------------------

## 8. Nieuwe development omgeving

Maak:

``` bash
cp -a vX.Y vX.Y+1-dev
```

Pas aan:

    AutoHunter
    Version: X.Y+1-dev
    Status: DEVELOPMENT

Update:

-   headers
-   templates
-   configuratie

------------------------------------------------------------------------

## 9. Development service

Nieuwe service:

    autohunter-web-dev.service

Wijst naar:

    /opt/carhunter/vX.Y+1-dev

------------------------------------------------------------------------

## 10. Git administratie

Voorbeeld tags:

    v2.8-production
    v2.9-dev-start
    v2.9-dev-web-isolated

------------------------------------------------------------------------

# Lessons Learned

## Database hoort bij de release

Een release is niet alleen code.

## Symlink bepaalt productie

De actieve versie wordt bepaald door:

    current -> release directory

## Services volgen versies niet automatisch

Systemd moet aangepast worden.

## Versies staan op meerdere plekken

Controleer:

-   Python bestanden
-   templates
-   config
-   docs
