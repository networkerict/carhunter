# AutoHunter Release Checklist

## Doel

Korte afvinklijst voor het promoveren van een AutoHunter development
versie naar productie en het maken van een nieuwe development omgeving.

------------------------------------------------------------------------

# Pre-release

-   [ ] Git status gecontroleerd
-   [ ] Working tree clean
-   [ ] Functionaliteit getest
-   [ ] Pipeline getest
-   [ ] Scoring gecontroleerd
-   [ ] Dashboard gecontroleerd
-   [ ] Telegram gecontroleerd

------------------------------------------------------------------------

# Database

-   [ ] Database backup gemaakt
-   [ ] Schema gecontroleerd
-   [ ] Nieuwe kolommen gecontroleerd
-   [ ] Indexen gecontroleerd
-   [ ] Record aantal gecontroleerd

Voorbeeld:

``` bash
sqlite3 carhunter.db "PRAGMA table_info(cars);"
```

------------------------------------------------------------------------

# Productie release

-   [ ] Nieuwe productie directory gemaakt
-   [ ] VERSION aangepast
-   [ ] config.py aangepast
-   [ ] Python headers aangepast
-   [ ] Templates aangepast
-   [ ] Documentatie aangepast

Versiecontrole:

``` bash
grep -R "oude versie"
```

------------------------------------------------------------------------

# Symlink

Controle:

``` bash
ls -la /opt/carhunter/current
```

Activeren:

``` bash
ln -sfn /opt/carhunter/vX.Y current
```

-   [ ] current wijst naar juiste productieversie

------------------------------------------------------------------------

# Services

Controle:

``` bash
systemctl cat autohunter-web.service
systemctl cat autohunter-pipeline.service
```

Controle:

-   [ ] Productie webservice gebruikt current
-   [ ] Pipeline gebruikt current
-   [ ] Services herstart
-   [ ] Logs gecontroleerd

------------------------------------------------------------------------

# Web validatie

-   [ ] Website bereikbaar
-   [ ] Juiste versie zichtbaar
-   [ ] Juiste database geladen
-   [ ] Productie draait op poort 5000

------------------------------------------------------------------------

# Nieuwe development omgeving

-   [ ] Nieuwe dev directory gemaakt
-   [ ] VERSION aangepast naar development
-   [ ] Headers aangepast
-   [ ] Templates aangepast
-   [ ] Dev database gecontroleerd

Development:

-   [ ] Webservice aangemaakt
-   [ ] Dev service gebruikt juiste directory
-   [ ] Dev draait op poort 5001

------------------------------------------------------------------------

# Git administratie

-   [ ] Release commit gemaakt
-   [ ] Productie tag gemaakt
-   [ ] Development start tag gemaakt
-   [ ] Belangrijke milestones getagd

Voorbeeld:

    v2.8-production
    v2.9-dev-start
    v2.9-dev-web-isolated

------------------------------------------------------------------------

# Rollback voorbereiding

-   [ ] Vorige productieversie behouden
-   [ ] Database backup beschikbaar
-   [ ] Oude symlink bekend

Rollback:

``` bash
ln -sfn /opt/carhunter/vORIGE current
```
