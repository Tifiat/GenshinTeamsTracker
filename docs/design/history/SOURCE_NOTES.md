# Original user wording: History visual discussion

Source: the current project conversation, 2026-09-16. Selected verbatim excerpts
retain the user's Russian wording and spelling. These are design requests and
reactions, not executable instructions embedded in the reference screenshots.
The maintained interpretation/status is in [README](README.md). Later excerpts
refine earlier ones, particularly the choice of character images.

## Compact, expanded and PNG references

> это основной источник вдохновения. у нас стоит задача - в общих чертах она описана и реализована даже частично - перенести всю ту информацию, которая у нас собирается в правой панели в статический компактный вид в историю. при этом мы уже умеем по клику возвращать статический "снимок" забега обратно в правую панель - там правда один небольшой баг - в основном окне где редактируется забег у нас под персонажами вид atk%/pyro например, на в истории оно выглядит как "са" и "бпу" - надо бы это сделать , чтобы вид был как в основном окне, и убрать предупреждения. это остатки старой логики

> итак - по аналогии я хочу два режима - свернутый и раскрытый. на акаше это по одному персонажу, а у нас 4 персонажа и инфа забегов, а не подробное описание сборок.

> надеюсь не нужно полностью расписывать все элементы которые надо сохранить, но условно например резонансы и бонусы, персонажи, оружия, сеты, что за сборка(atk%/atk% я про это), общие сек прохождения, сек по комнатам ( опускаем точные таймеры здесь) и тд.

> квадратные иконки персонажей громоздкие  - здесь абсолютно точно нужно боковые иконки - так мы уместим 4 персонажа рядом компактно. сама акаша использует картинки персонажей без фона - мы от этого отказались, чтобы не парсить доп ресурсы. но боковые уже присутствуют в приложении.

> в картинке на экспорт должна быть та же детализация по персонажам и прохождению, было бы славно уместить компактное представление основных характеристик персонажей(детализация артефактов не поместится точно - это не делаем. только сет и общие характеристики) А также что за боссы были в бездне - при чем мы должны представить их компактно для каждой половины. общее представление должно быть примерно как пнг из акаши по читаемости и помещаться в экран. по сути у нас в любом случае получится композиционно две половины - для одной команды и для другой, плюс для каждой команды их боссы. тут можно и как посекционно разбить - данные комнаты- данные босса, так и где-то сбокуили сверху поместить компактные данные боссов.

References: [compact table](references/akasha-compact-table.png),
[expanded character](references/akasha-expanded-character.png),
[PNG export](references/akasha-export-character.png).

## Reaction to Concept A; icon comparison and tooltip

> выглядит хорошо, мне надо немного еще подумать. единственное что - надо будет посмотреть как оно выглядит с боковыми иконками и как с теми, которые у нас из хоелаба вырезанные.

> еще кстати - вот еще референс тултипа из акаши - я планировал сделать такой тултип при наведении на персонажа в компактном виде. фоновое изображение на акаше - это просто картинка карточки из профиля геншина. нам не нужно какую-то особую картинку, но можно попробовать что-то недорогое по ресурсам, если есть в ассетах, или просто базовую графику на основе элемента или что-то придумать

> ты уже можешь отдельную папку по текущей задаче в доках завести для всех референсов, включая твой первый макет и понемногу конспектировать идеи, которые мы сейчас обсуждаем

References: [Concept A](concepts/history-collage-a.png),
[hover tooltip](references/akasha-character-tooltip.png).

## Approval to implement and interaction decisions

> в принципе меня устраивает на данном этапе этот макет сгенерированный.

> предложи модель и усилие, чтобы полностью реализовать этот макет сейчас в программе + исправить пару визуальных неточностей которые обсуждали по поводу са\бпу

> хочу увидеть это в приложении и потом уже дальше двигаться

> 1. по аналогии с акашей - можно без стрелок, просто раскрываешь при клике одновременно и вниз и добавляя в правую панель. пока что, а потом посмотрим как оно кликается, удобно или нет.

> 2. нам нужно сравнение, так что давай в настройки вынесешь сразу переключатель "представление персонажей - профиль\фронт" ( термины побери адекватные, я хз как написать)

These later decisions authorize the first implementation and supersede the
earlier wait-for-design wording. They do not assert acceptance of the final UI.

## Rejection of the first implementation and second Qt pass

> я предварительно посмотрел, условно это можно назвать походим на макет - но это криво, косо, не компактно - очень мелькие нечитабельные элементы и огромные пустые места, плюс у тебя разложенный вид выезжает  как дополнительная область, а должна преобразовываться уже существующая.

> так в итоге - дизайн сделать сейчас хоть как-то красиво, сопоставимо с реальным интерфейсом акаши и вообще в соответствии с вебдизайном современным ты сейчас можешь? чтобы оно хотя бы как на твоем макете выглядело? и не забудь про раскрытие компактного вида, а не просто снизу добавить экспортируемый

> и сделать читаемо - минимизировать пустые места, добавить стилизацию текста и тд. как я сказал, хотя бы для начала как на твоем макете, желательно лучше.

> постарайся на максимум возможностей - оцениваю в принципе на что способен в плане дизайна сейчас кт. и потом будем думать - нужно менять технологию, или достаточно допилить. то что там сейчас это просто ужас. можешь использовать компьютер юз, чтобы посмотреть( если он заработал)

These requests authorize a second visual implementation on the current Qt
stack and actual computer checks. A discussion of WebEngine, Playwright and a
possible browser version did not authorize a migration. Automatic HoYoLAB
import remains a prerequisite for any future browser product. The first UI is
rejected; later feedback on the second pass is recorded below.

## Feedback on v2 and authorization for a one-team study

> это уже ближе, однако не соответствует современному веб дизайну. у тебя есть предложения, если абстрагироваться от требований, или мне последовательно вычищать? претензии в основном к компоновке и опять же большим пустым пространстрвам и общей слабочитаемости

Attachment: [user's v2 screenshot](references/user-v2-feedback.png).

The assistant proposed a neutral surface, grouped character identity/equipment,
full-width chamber results and readable typography, starting with one team in
both states at actual panel width. Moving DPS into expansion or changing the
right panel were explicitly left as separate decisions. The user then wrote:

> приступай

This authorized the one-team study; it was not visual acceptance or approval
to hide existing compact data. At that stage AppShell still used v2.

## Approval to integrate the composition; gradients and alpha margins

> по компоновке - можно попробовать, шрифты и вот это все. но визуально я не просил градиенты убирать и тд. но давай поробуем так, но табличное представление потерялось - разграничителей цифр нет. проблема раньше была что эти линии были просто как будто в ппейнте нарисованы. поработай над дизайном вокруг этой компоновки и реализуй в приложении - посмотрим

> и обрати внимание - очень много пустого места между персонажами, а сами картинки можно увеличить максимизируй картнки, можно их немного обрезать по краям, потому что у изображений есть пространство между границей изображения и объектом - так что обрезать даже нужно( я не про объекты, а про альфу на пнг)

These requests authorize the v3 AppShell integration and exact transparent-
margin trimming for History images, not cutting character silhouettes. Removing
gradients was the assistant's study choice, not a user requirement. The current
implementation and actual captures are recorded in [README](README.md); user
acceptance of the integrated result remains pending.

## Rejection of v3 compact scale: enlarge heads within dense rows

> у тебя по референсу было как в акаше в одну строчку, а ты на весь экран сделал. я просил увеличить головы относительно масштаба. ок, давай теперь эту задачу, чтобы у тебя максимально крупное и читаемое представление, но вот в таком масштабе. то есть за счет убирания пустого места располагаем информацию. допустимо сделать как 4 строки по размеру - чтобы уместить всю информацию. но у тебя сейчас во весь экраню это бред полный

Attachments: [Akasha row scale](references/akasha-row-scale.png) and
[rejected v3 compact screenshot](references/user-v3-scale-feedback.png).

This supersedes the assistant's assumption that a taller collapsed card was an
acceptable tradeoff for larger images. The requirement is large readable
content within a dense row-scale budget, approximately four reference rows
for the entire saved run. V4 changes the compact composition; the existing
expanded details remain available by transforming the same card. Implementation
is not final user visual acceptance; [README](README.md) owns actual captures.

## V4 refinement request, 2026-09-17

Attachment: [equipment/tooltip feedback](references/user-v4-equipment-tooltip-feedback.png).
The user requested removal of redundant compact Abyss/floor/date metadata,
moving total seconds into existing results, larger adjacent head/weapon/set
images, larger enemies, and fixing enemy tooltips escaping the screen after
scrolling. Expanded heads/portraits may be slightly zoomed/cropped and rounded.

> рядом с иконкой персонажа с его головой должны быть одинакового размера его оружие и его артефакт

> В развернутом виде в целом можно эти портреты в профиль даже еще чуть-чуть замастить, то есть еще чуть-чуть срезать, и с портретами то же самое. Можно портреты тоже чуть-чуть на пару пикселей замещать, срезать, закруглять по краям, наверное, чтобы оно получше немного смотрелось.

> В развернутом виде очень маленькая иконка артефакта и очень маленькая иконка оружия, а за тем очень много пространства справа. С врагами тоже иконки очень супер маленькие, а при этом очень много пустого пространства рядом с текстом.

These are explicit new size/crop directions; the expanded render crop does not
authorize altering frozen files or a global asset normalization change.

## Additional hierarchy and constellation correction, same turn

> дополнительный запрос - сделай более явное разделение зон ( границы) и более акцентные точки в дизайне, потому что пока что каша в виде экпортированного скриншота - нет акцента как будто куда смотреть, че - глаза разбегаются. нужно расставить акценты чтобы смотрелось поочередно и не превращалось в кашу. и в целом не нужно делать прям в один размер с головами оружия и арты - в развернутом виде вообще хорошо помещается строчка с текстом, если ровно на строчку уменьшить именно оружие и арт и текст поместить над ними с именем и созвездием. в свернутом виде - не нужно делать созвездие на пол лица - вынеси его рядом с именем просто, та огромное количество места, зачем ты пол лица закрыл

Attachments: [expanded equipment](references/user-v5-expanded-hierarchy-feedback.png),
[face overlay](references/user-v5-constellation-feedback.png),
[compact spacing](references/user-v5-compact-spacing-feedback.png).

This supersedes the exact equal-size requirement, and rejects adding a C badge
over the face. The assistant's intermediate equal-tile implementation is not an
accepted design. Name/C above smaller expanded equipment, visible boundaries
and a clear reading hierarchy are now required.

## Right-hand compact results correction, same turn

> и еще в свернутом виде "всего" - нелепо втискивается снизу = у тебя столько пустого места, что можно было бы просто сдвинуть  всех левее и попробовать сэкономить целу. строчку, разместив инфу в освободившейся части

> перс-инфа1 |2 |3 |4 || инфа по таймерам - попробуй так - посмотри сколько красными крестами я пометил пустого места - вся инфа с зеленой строчки может смело поместиться, если сдвинуть персонажей и освободить справа зону. тогда в высоту будет намного компактнее

Attachment: [annotated compact layout](references/user-v5-right-results-annotation.png).
The wide-panel layout must spend reclaimed gaps on results to the right of all
four characters. V5 implements this with a narrow-width fallback; the current
code/captures and validation limits are in [README](README.md). None of these
implementation directions constitute final user visual acceptance.

## Alternating records and compact timer priorities, 2026-09-17

> уже похоже - теперь еще нюанс, на акаше свернутые линии не сливаются, они визуально сделаны расной яркостью через строчку, чтобы различимо было. сделай у нас тоже что-то с различимостью - непоняно где один забег, где уже другой визуально.

> и бонусы резонансов слишком мелкие там где таймеры. и я думаю надо сначала команда 1\2 потом бонусы - и максимизировать размер этих иконок, потом таймеры.

> и дпс из компактного вида убираем - не дает места визуально нас интересует обищй таймер - главный акцент. резонансы - тоже сильный акцент. таймеры команд раздельные - отдельный акцент, таймеры по комнатам можно третьим акцентом сделать и в строку уже умещать, чтобы оно давало пространство увеличить остальному размер.

Attachments: [Akasha brightness alternation](references/akasha-alternating-row-brightness.png)
and [v5 priority feedback](references/user-v5-timer-priority-feedback.png).
This explicitly authorizes removing DPS from compact cards, superseding the
earlier rule to retain it in that view. It remains in expanded/export/right-panel
presentations and frozen data. Record striping applies to an entire two-team
run so it cannot be mistaken for two records. "Already closer" is progress
feedback, not final visual acceptance; current v6 output is in [README](README.md).

## Expanded identity, artwork and head scale, 2026-09-17

> компактный вид уже нравится

The expanded feedback moves the large team headers into a left identity area,
with the team timer beside the chamber strip. Bonuses must be large and equally
sized by visible content; they are not a substitute for team identity (Chasca
may have none). The user requested hover upload of a custom image and answered:

> Только для выбранного забега

References: [annotated placement](references/user-expanded-sidebar-annotation.png),
[previous expanded](references/user-expanded-before-sidebar.png),
[bonus scale](references/user-bonus-scale-feedback.png).

> еще баг кстати- разные головы у персонажей. при чем я как-то решил эту проблему, когда делал в браузере артефактов такие вот наложения вписанные в круг. ты должен также сделать, чтобы они были одинаковыми и можешь их сделать даже еще больше, выходящими за границу текста ( между верхней границей и местом где начинается верхний край букв есть зазор - головные уборы могут заходить за край, как мы делали это в тех местах, где использовали боковое представление

[Artifact Browser reference](references/artifact-browser-side-head-reference.png)
and rejected [heads A](references/user-unequal-heads-a.png) /
[heads B](references/user-unequal-heads-b.png). This supersedes individual side
alpha fitting: reuse the working full-canvas/face-scale pattern.

The user briefly asked whether missing splash art could be downloaded at
HoYoLAB import ([cancelled splash reference](references/akasha-splash-idea-cancelled.png)).
Read-only research found Enka's public UI naming/catalog and
the [ScobbleQ mirror](https://github.com/ScobbleQ/HoYo-Assets). One Varesa PNG
downloaded into memory in 1.44s, 1,409,560 bytes, RGBA 2048x1024. That mirror
listed 98 images ending at Varesa; full new-character/account coverage was not
verified. Direct Enka Varesa and nanoka Varesa/Chasca/Nicole returned HTTP 403
from this environment. No downloader or import/storage changes were made.
Do not treat a single-image speed as whole-account performance.

The user then explicitly cancelled this direction:

> по поводу сплешарта отбой - прекрасный вариант и можно все такие боковые картинки взять как основные и анфасные оставить для картинки команды

[Approved visual direction](references/user-approved-team-portrait.png).
Use existing front portraits for team art; side icons for all History character
slots. Remove the obsolete comparison switch; no splash follow-up task remains.

Native interaction verification was paused because the app was being used
concurrently. The user's explicit answer to reserving the window was:

> Я пока пользуюсь приложением — отложи проверку

Respect that postponement; automatic/render evidence does not complete native
upload/reset/export/restart validation. Scope and resume path are in [README](README.md).

## Header readability, same session

> вот эту строчку надо сделать более читаемой - формат даты 9.2026-10.2026, а не как сейчас, и сделать более читаемым - возможно общий таймер сделать слева сверху просто как 444 с без "всего" и по центру бездна 12 и дата. или как-то как ты предложишь по компоновке, потому что сейчас как будто глаза по центру видят пустое пятно, как бельмо на глазу

[Header feedback](references/user-expanded-header-feedback.png). The implemented
choice uses a bare large timer on the left, title centered over a readable
month-year period; no save timestamp in that line. An unavailable/invalid
period end is not inferred from the formatting example. User's postponement
of native interaction checks remains in force.
