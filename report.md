# teacher_courses.html 관리자 포털 버튼 추가 — admin 겸직 교수/조교 직접 진입점 보고

> 2026-06-13 · 변경 = **버튼 1개 + 라우트 인자 1개**. 절대 불변(_postLoginDest·/portal 게이트·home/slides·기존 teacher 기능) 무변경.

## 변경 1 — 백엔드: /teacher/courses 가 is_admin 전달
`server_render.py` `teacher_courses_page()` (라우트 `@app.route('/teacher/courses')`, def L3161).
**정확한 위치**: position 게이트(`if pos not in ('교수','조교'): return redirect('/home')`) **직후**, `render_template` 직전. diff:
```diff
     if pos not in ('교수', '조교'):
         return redirect('/home')
-    return render_template('teacher_courses.html', is_professor=(pos == '교수'))
+    # [admin 겸직 진입점] 상단바 '관리자 포털' 버튼 노출 여부 — /home(L862)과 '동일한 호출'
+    #   _is_institution_admin(=__ADMIN__ roster 행 존재, §9)로 판정. 새 판정 로직·role 단독 우회 없음.
+    is_admin = _is_institution_admin(g.user_id, g.institution_id)
+    return render_template('teacher_courses.html', is_professor=(pos == '교수'), is_admin=is_admin)
```
- **/home(L862)과 글자까지 동일한 호출**: `is_admin = _is_institution_admin(g.user_id, g.institution_id)` (코드베이스에 이 라인 정확히 **2곳** = /home + /teacher/courses).
- 기존 `is_professor=(pos=='교수')` 인자·position 게이트·conn 처리 무변경. `is_admin` 인자만 추가.
- `_is_institution_admin` 함수 **본문 무변경**(diff는 teacher 라우트 hunk 1개뿐).

## 변경 2 — 프론트: teacher_courses.html 상단바 버튼
`templates/teacher_courses.html` `.tb-right`(L33–37):
```diff
   <div class="tb-right">
+    {% if is_admin %}<a class="tb-link" href="/portal"><i class="ti ti-shield"></i>관리자 포털</a>{% endif %}
     <a class="tb-link" href="/mypage"><i class="ti ti-user"></i>마이페이지</a>
     <a class="tb-link" id="btn-logout" onclick="doLogout()"><i class="ti ti-logout"></i>로그아웃</a>
   </div>
```
- **노출 조건 = `{% if is_admin %}`** — home.html(L126)과 **동일 게이트·동일 변수**(둘 다 `_is_institution_admin`). 새 판정 없음(§0).
- href `/portal`·라벨 `관리자 포털` 동일. 배치 순서 = home(관리자 포털 → 마이페이지)과 일관되게 **마이페이지 앞**.

### ★ home과 버튼 마크업 동일 여부 (요청 항목)
**의도·게이트·목적지는 동일하나, CSS 클래스는 의도적으로 다름**:
- home.html: `<a class="btn-nav ghost" href="/portal">관리자 포털</a>` (home 인라인 `.btn-nav` 스타일)
- teacher: `<a class="tb-link" href="/portal"><i class="ti ti-shield"></i>관리자 포털</a>` (teacher 상단바 `.tb-link` 스타일 + Tabler shield 아이콘)
- **이유**: `.btn-nav`/`.ghost`는 home.html 전용 인라인 클래스로 **teacher_courses.html(lms.css `.topbar`/`.tb-link` 사용)엔 정의가 없음** → 그대로 복제하면 **무스타일 링크**가 됨. 지시의 "상단바 같은 줄·일관되게"(마이페이지/로그아웃과 동일 행) 요건을 충족하려면 상단바 네이티브 `.tb-link`(마이페이지=`.tb-link`+ti-user 패턴)로 맞춰야 함. **`{% if is_admin %}`·`href="/portal"`·라벨은 글자까지 동일**, 시각 클래스만 그 화면 컨벤션에 맞춤.
> 만약 무스타일이라도 마크업을 글자까지 동일(`class="btn-nav ghost"`)하게 원하시면 한 줄로 되돌릴 수 있습니다 — 알려주세요.

## 절대 불변 — 검증 통과
| 항목 | 결과 |
|------|------|
| `static/js/login_terminal.js`(_postLoginDest 착지 분기) | **UNCHANGED** |
| `templates/home.html` | **UNCHANGED** |
| `templates/slides.html` | **UNCHANGED** |
| `_is_institution_admin` 함수 본문 | 무변경(diff=teacher 라우트 hunk 1개) |
| /portal 서버 게이트 | 무변경(버튼은 링크일 뿐, 권한은 서버 재검증) |
| teacher 기존 기능·fetch·수업 카드·다른 링크 | 무변경(.tb-right에 1줄 추가만) |
| is_professor 인자·position 게이트 | 무변경 |

## 동작 검증(로직 추적)
- **admin 겸직 교수/조교**(roster에 `__ADMIN__` 행 존재): `_is_institution_admin`=True → 상단바 '관리자 포털' 노출 → 클릭 시 `/portal`(서버 게이트도 동일 함수로 통과).
- **비-admin 교수/조교**(`__ADMIN__` 행 없음): `_is_institution_admin`=False → 버튼 미노출.
- home의 is_admin 조건 = teacher의 is_admin 조건 = **동일 함수 `_is_institution_admin` 동일 인자**.
- _postLoginDest(②: 교수/조교→/teacher/courses)·/portal 게이트 **diff 0**.

## 정적 검증
- Jinja parse OK(teacher_courses.html) · Python 구문 OK(server_render.py).
- `is_admin = _is_institution_admin(g.user_id, g.institution_id)` 코드베이스 2곳(=/home·/teacher/courses) 일치.

> 실측: CEO EC2 배포 후 admin 겸직 교수/조교 계정으로 /teacher/courses 진입 → 버튼 노출·클릭→/portal, 비-admin 교수/조교는 미노출 확인(§20).
