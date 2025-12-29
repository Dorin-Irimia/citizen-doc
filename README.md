# Citizen-Doc  
### Aplicație web pentru gestionarea documentelor cetățenilor

---

## 📌 Descriere generală

**Citizen-Doc** este o aplicație web dezvoltată în Python (framework Django) care permite
**încărcarea, stocarea și vizualizarea documentelor** într-un mod simplu și centralizat.

Proiectul reprezintă un **MVP (Minimum Viable Product)** și are rol demonstrativ,
fiind potrivit pentru:
- prototipuri de digitalizare
- demonstrații în instituții publice
- proiecte educaționale
- prezentări pentru finanțări

Aplicația este concepută astfel încât **o persoană fără experiență tehnică** să poată
înțelege ce face și cum se folosește.

---

## 📖 Cuprins

1. [Ce problemă rezolvă aplicația](#-ce-problemă-rezolvă-aplicația)
2. [Funcționalități implementate](#-funcționalități-implementate)
3. [Pagini disponibile în aplicație](#-pagini-disponibile-în-aplicație)
4. [Ghid de utilizare (User Guide – pe înțelesul cetățenilor)](#-ghid-de-utilizare-user-guide)
5. [Arhitectură tehnică (Technical Architecture)](#-arhitectură-tehnică-technical-architecture)
6. [Structura proiectului](#-structura-proiectului)
7. [Instalare și rulare](#-instalare-și-rulare)
8. [Starea actuală a proiectului](#-starea-actuală-a-proiectului)
9. [Limitări cunoscute](#-limitări-cunoscute)
10. [Posibile extinderi viitoare](#-posibile-extinderi-viitoare)

---

## 🎯 Ce problemă rezolvă aplicația

În multe situații, documentele sunt:
- depuse fizic
- greu de urmărit
- dispersate
- dificil de centralizat

Citizen-Doc oferă o **soluție simplă de digitalizare**, unde documentele pot fi:
- încărcate online
- stocate centralizat
- consultate rapid

---

## ⚙️ Funcționalități implementate

### 📤 Încărcare documente
- utilizatorul poate încărca fișiere printr-un formular web
- documentele sunt salvate pe server
- informațiile despre document sunt salvate într-o bază de date

### 📄 Vizualizare documente
- afișarea unei liste cu documentele existente
- acces direct la fișierele încărcate

### 🗂️ Administrare
- panou de administrare Django
- gestionarea documentelor
- gestionarea utilizatorilor (administrator)

### 🐳 Containerizare
- rulare rapidă folosind Docker
- configurare minimă pentru pornire

---

## 🌐 Pagini disponibile în aplicație

| Pagină | URL | Descriere |
|------|-----|-----------|
| Home | `/` | Pagina principală |
| Upload document | `/upload/` | Încărcare document |
| Listă documente | `/documents/` | Vizualizare documente |
| Admin | `/admin/` | Panou de administrare |

---

## 👤 Ghid de utilizare (User Guide)

### 1. Accesarea aplicației
Aplicația se accesează dintr-un browser (Chrome, Edge, Firefox).
La deschidere, utilizatorul vede pagina principală.

### 2. Încărcarea unui document
- se accesează pagina **Upload document**
- se selectează fișierul din calculator
- se apasă butonul de trimitere

### 3. Vizualizarea documentelor
- se accesează pagina **Listă documente**
- sunt afișate toate documentele încărcate

### 4. Ce trebuie să știe utilizatorul
- aplicația este una demonstrativă
- documentele nu sunt validate automat
- nu există conturi individuale pentru cetățeni

---

## 🏗️ Arhitectură tehnică (Technical Architecture)

### Tehnologii folosite
- **Backend:** Python + Django
- **Frontend:** HTML (Django Templates)
- **Bază de date:** SQLite
- **Containerizare:** Docker & Docker Compose

### Arhitectură generală

## 🛣️ Etapele următoare de dezvoltare

Acest proiect reprezintă un **MVP (Minimum Viable Product)**. Următorii pași logici pentru evoluția aplicației sunt:

### 1️⃣ Ghid pentru utilizatori (User Guide)
- document dedicat cetățenilor
- explicații pas cu pas despre utilizarea aplicației
- limbaj non-tehnic
- potrivit pentru tipărire sau distribuire digitală

### 2️⃣ Arhitectură tehnică detaliată (Technical Architecture)
- document destinat dezvoltatorilor și evaluatorilor tehnici
- descriere clară a componentelor aplicației
- fluxuri de date
- limitări tehnice asumate

### 3️⃣ Transformarea într-un produs real pentru primării
- autentificare utilizatori
- roluri (cetățean / funcționar / administrator)
- flux de aprobare documente
- securitate și audit
- integrare cu sisteme instituționale
- respectarea cerințelor legale

Acești pași permit evoluția proiectului dintr-un **demo funcțional** într-o
**platformă utilizabilă în mediul instituțional real**.
