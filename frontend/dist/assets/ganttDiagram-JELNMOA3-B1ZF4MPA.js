import{g as ce,s as le,q as ue,p as de,a as fe,b as he,_ as c,c as nt,d as ht,av as me,aw as ke,ax as ye,e as ge,P as ve,ay as pe,l as et,az as Te,aA as Pt,aB as Vt,aC as be,aD as xe,aE as we,aF as _e,aG as De,aH as Se,aI as Ce,aJ as Nt,aK as Rt,aL as Bt,aM as zt,aN as jt,aO as Ee,k as Ie,j as Me,y as Ae,u as Fe}from"./mermaid-BdN0_db4.js";import{l as Xt,n as Ut,d as V,o as $e,p as Le}from"./element-plus-BU7CkAdN.js";import"./vue-vendor-D7k_BbKJ.js";var Kt={exports:{}};(function(t,r){(function(i,n){t.exports=n()})(Xt,function(){var i="day";return function(n,a,k){var T=function(A){return A.add(4-A.isoWeekday(),i)},S=a.prototype;S.isoWeekYear=function(){return T(this).year()},S.isoWeek=function(A){if(!this.$utils().u(A))return this.add(7*(A-this.isoWeek()),i);var D,$,L,W,O=T(this),_=(D=this.isoWeekYear(),$=this.$u,L=($?k.utc:k)().year(D).startOf("year"),W=4-L.isoWeekday(),L.isoWeekday()>4&&(W+=7),L.add(W,i));return O.diff(_,"week")+1},S.isoWeekday=function(A){return this.$utils().u(A)?this.day()||7:this.day(this.day()%7?A:A-7)};var Y=S.startOf;S.startOf=function(A,D){var $=this.$utils(),L=!!$.u(D)||D;return $.p(A)==="isoweek"?L?this.date(this.date()-(this.isoWeekday()-1)).startOf("day"):this.date(this.date()-1-(this.isoWeekday()-1)+7).endOf("day"):Y.bind(this)(A,D)}}})})(Kt);var We=Kt.exports;const Oe=Ut(We);var Jt={exports:{}};(function(t,r){(function(i,n){t.exports=n()})(Xt,function(){var i,n,a=1e3,k=6e4,T=36e5,S=864e5,Y=/\[([^\]]+)]|Y{1,4}|M{1,4}|D{1,2}|d{1,4}|H{1,2}|h{1,2}|a|A|m{1,2}|s{1,2}|Z{1,2}|SSS/g,A=31536e6,D=2628e6,$=/^(-|\+)?P(?:([-+]?[0-9,.]*)Y)?(?:([-+]?[0-9,.]*)M)?(?:([-+]?[0-9,.]*)W)?(?:([-+]?[0-9,.]*)D)?(?:T(?:([-+]?[0-9,.]*)H)?(?:([-+]?[0-9,.]*)M)?(?:([-+]?[0-9,.]*)S)?)?$/,L={years:A,months:D,days:S,hours:T,minutes:k,seconds:a,milliseconds:1,weeks:6048e5},W=function(I){return I instanceof G},O=function(I,p,f){return new G(I,f,p.$l)},_=function(I){return n.p(I)+"s"},J=function(I){return I<0},B=function(I){return J(I)?Math.ceil(I):Math.floor(I)},Q=function(I){return Math.abs(I)},j=function(I,p){return I?J(I)?{negative:!0,format:""+Q(I)+p}:{negative:!1,format:""+I+p}:{negative:!1,format:""}},G=function(){function I(f,u,y){var g=this;if(this.$d={},this.$l=y,f===void 0&&(this.$ms=0,this.parseFromMilliseconds()),u)return O(f*L[_(u)],this);if(typeof f=="number")return this.$ms=f,this.parseFromMilliseconds(),this;if(typeof f=="object")return Object.keys(f).forEach(function(o){g.$d[_(o)]=f[o]}),this.calMilliseconds(),this;if(typeof f=="string"){var v=f.match($);if(v){var m=v.slice(2).map(function(o){return o!=null?Number(o):0});return this.$d.years=m[0],this.$d.months=m[1],this.$d.weeks=m[2],this.$d.days=m[3],this.$d.hours=m[4],this.$d.minutes=m[5],this.$d.seconds=m[6],this.calMilliseconds(),this}}return this}var p=I.prototype;return p.calMilliseconds=function(){var f=this;this.$ms=Object.keys(this.$d).reduce(function(u,y){return u+(f.$d[y]||0)*L[y]},0)},p.parseFromMilliseconds=function(){var f=this.$ms;this.$d.years=B(f/A),f%=A,this.$d.months=B(f/D),f%=D,this.$d.days=B(f/S),f%=S,this.$d.hours=B(f/T),f%=T,this.$d.minutes=B(f/k),f%=k,this.$d.seconds=B(f/a),f%=a,this.$d.milliseconds=f},p.toISOString=function(){var f=j(this.$d.years,"Y"),u=j(this.$d.months,"M"),y=+this.$d.days||0;this.$d.weeks&&(y+=7*this.$d.weeks);var g=j(y,"D"),v=j(this.$d.hours,"H"),m=j(this.$d.minutes,"M"),o=this.$d.seconds||0;this.$d.milliseconds&&(o+=this.$d.milliseconds/1e3,o=Math.round(1e3*o)/1e3);var l=j(o,"S"),h=f.negative||u.negative||g.negative||v.negative||m.negative||l.negative,d=v.format||m.format||l.format?"T":"",b=(h?"-":"")+"P"+f.format+u.format+g.format+d+v.format+m.format+l.format;return b==="P"||b==="-P"?"P0D":b},p.toJSON=function(){return this.toISOString()},p.format=function(f){var u=f||"YYYY-MM-DDTHH:mm:ss",y={Y:this.$d.years,YY:n.s(this.$d.years,2,"0"),YYYY:n.s(this.$d.years,4,"0"),M:this.$d.months,MM:n.s(this.$d.months,2,"0"),D:this.$d.days,DD:n.s(this.$d.days,2,"0"),H:this.$d.hours,HH:n.s(this.$d.hours,2,"0"),m:this.$d.minutes,mm:n.s(this.$d.minutes,2,"0"),s:this.$d.seconds,ss:n.s(this.$d.seconds,2,"0"),SSS:n.s(this.$d.milliseconds,3,"0")};return u.replace(Y,function(g,v){return v||String(y[g])})},p.as=function(f){return this.$ms/L[_(f)]},p.get=function(f){var u=this.$ms,y=_(f);return y==="milliseconds"?u%=1e3:u=y==="weeks"?B(u/L[y]):this.$d[y],u||0},p.add=function(f,u,y){var g;return g=u?f*L[_(u)]:W(f)?f.$ms:O(f,this).$ms,O(this.$ms+g*(y?-1:1),this)},p.subtract=function(f,u){return this.add(f,u,!0)},p.locale=function(f){var u=this.clone();return u.$l=f,u},p.clone=function(){return O(this.$ms,this)},p.humanize=function(f){return i().add(this.$ms,"ms").locale(this.$l).fromNow(!f)},p.valueOf=function(){return this.asMilliseconds()},p.milliseconds=function(){return this.get("milliseconds")},p.asMilliseconds=function(){return this.as("milliseconds")},p.seconds=function(){return this.get("seconds")},p.asSeconds=function(){return this.as("seconds")},p.minutes=function(){return this.get("minutes")},p.asMinutes=function(){return this.as("minutes")},p.hours=function(){return this.get("hours")},p.asHours=function(){return this.as("hours")},p.days=function(){return this.get("days")},p.asDays=function(){return this.as("days")},p.weeks=function(){return this.get("weeks")},p.asWeeks=function(){return this.as("weeks")},p.months=function(){return this.get("months")},p.asMonths=function(){return this.as("months")},p.years=function(){return this.get("years")},p.asYears=function(){return this.as("years")},I}(),Z=function(I,p,f){return I.add(p.years()*f,"y").add(p.months()*f,"M").add(p.days()*f,"d").add(p.hours()*f,"h").add(p.minutes()*f,"m").add(p.seconds()*f,"s").add(p.milliseconds()*f,"ms")};return function(I,p,f){i=f,n=f().$utils(),f.duration=function(g,v){var m=f.locale();return O(g,{$l:m},v)},f.isDuration=W;var u=p.prototype.add,y=p.prototype.subtract;p.prototype.add=function(g,v){return W(g)?Z(this,g,1):u.bind(this)(g,v)},p.prototype.subtract=function(g,v){return W(g)?Z(this,g,-1):y.bind(this)(g,v)}}})})(Jt);var Ye=Jt.exports;const Pe=Ut(Ye);var xt=function(){var t=c(function(m,o,l,h){for(l=l||{},h=m.length;h--;l[m[h]]=o);return l},"o"),r=[6,8,10,12,13,14,15,16,17,18,20,21,22,23,24,25,26,27,28,29,30,31,33,35,36,38,40],i=[1,26],n=[1,27],a=[1,28],k=[1,29],T=[1,30],S=[1,31],Y=[1,32],A=[1,33],D=[1,34],$=[1,9],L=[1,10],W=[1,11],O=[1,12],_=[1,13],J=[1,14],B=[1,15],Q=[1,16],j=[1,19],G=[1,20],Z=[1,21],I=[1,22],p=[1,23],f=[1,25],u=[1,35],y={trace:c(function(){},"trace"),yy:{},symbols_:{error:2,start:3,gantt:4,document:5,EOF:6,line:7,SPACE:8,statement:9,NL:10,weekday:11,weekday_monday:12,weekday_tuesday:13,weekday_wednesday:14,weekday_thursday:15,weekday_friday:16,weekday_saturday:17,weekday_sunday:18,weekend:19,weekend_friday:20,weekend_saturday:21,dateFormat:22,inclusiveEndDates:23,topAxis:24,axisFormat:25,tickInterval:26,excludes:27,includes:28,todayMarker:29,title:30,acc_title:31,acc_title_value:32,acc_descr:33,acc_descr_value:34,acc_descr_multiline_value:35,section:36,clickStatement:37,taskTxt:38,taskData:39,click:40,callbackname:41,callbackargs:42,href:43,clickStatementDebug:44,$accept:0,$end:1},terminals_:{2:"error",4:"gantt",6:"EOF",8:"SPACE",10:"NL",12:"weekday_monday",13:"weekday_tuesday",14:"weekday_wednesday",15:"weekday_thursday",16:"weekday_friday",17:"weekday_saturday",18:"weekday_sunday",20:"weekend_friday",21:"weekend_saturday",22:"dateFormat",23:"inclusiveEndDates",24:"topAxis",25:"axisFormat",26:"tickInterval",27:"excludes",28:"includes",29:"todayMarker",30:"title",31:"acc_title",32:"acc_title_value",33:"acc_descr",34:"acc_descr_value",35:"acc_descr_multiline_value",36:"section",38:"taskTxt",39:"taskData",40:"click",41:"callbackname",42:"callbackargs",43:"href"},productions_:[0,[3,3],[5,0],[5,2],[7,2],[7,1],[7,1],[7,1],[11,1],[11,1],[11,1],[11,1],[11,1],[11,1],[11,1],[19,1],[19,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,2],[9,2],[9,1],[9,1],[9,1],[9,2],[37,2],[37,3],[37,3],[37,4],[37,3],[37,4],[37,2],[44,2],[44,3],[44,3],[44,4],[44,3],[44,4],[44,2]],performAction:c(function(o,l,h,d,b,s,F){var e=s.length-1;switch(b){case 1:return s[e-1];case 2:this.$=[];break;case 3:s[e-1].push(s[e]),this.$=s[e-1];break;case 4:case 5:this.$=s[e];break;case 6:case 7:this.$=[];break;case 8:d.setWeekday("monday");break;case 9:d.setWeekday("tuesday");break;case 10:d.setWeekday("wednesday");break;case 11:d.setWeekday("thursday");break;case 12:d.setWeekday("friday");break;case 13:d.setWeekday("saturday");break;case 14:d.setWeekday("sunday");break;case 15:d.setWeekend("friday");break;case 16:d.setWeekend("saturday");break;case 17:d.setDateFormat(s[e].substr(11)),this.$=s[e].substr(11);break;case 18:d.enableInclusiveEndDates(),this.$=s[e].substr(18);break;case 19:d.TopAxis(),this.$=s[e].substr(8);break;case 20:d.setAxisFormat(s[e].substr(11)),this.$=s[e].substr(11);break;case 21:d.setTickInterval(s[e].substr(13)),this.$=s[e].substr(13);break;case 22:d.setExcludes(s[e].substr(9)),this.$=s[e].substr(9);break;case 23:d.setIncludes(s[e].substr(9)),this.$=s[e].substr(9);break;case 24:d.setTodayMarker(s[e].substr(12)),this.$=s[e].substr(12);break;case 27:d.setDiagramTitle(s[e].substr(6)),this.$=s[e].substr(6);break;case 28:this.$=s[e].trim(),d.setAccTitle(this.$);break;case 29:case 30:this.$=s[e].trim(),d.setAccDescription(this.$);break;case 31:d.addSection(s[e].substr(8)),this.$=s[e].substr(8);break;case 33:d.addTask(s[e-1],s[e]),this.$="task";break;case 34:this.$=s[e-1],d.setClickEvent(s[e-1],s[e],null);break;case 35:this.$=s[e-2],d.setClickEvent(s[e-2],s[e-1],s[e]);break;case 36:this.$=s[e-2],d.setClickEvent(s[e-2],s[e-1],null),d.setLink(s[e-2],s[e]);break;case 37:this.$=s[e-3],d.setClickEvent(s[e-3],s[e-2],s[e-1]),d.setLink(s[e-3],s[e]);break;case 38:this.$=s[e-2],d.setClickEvent(s[e-2],s[e],null),d.setLink(s[e-2],s[e-1]);break;case 39:this.$=s[e-3],d.setClickEvent(s[e-3],s[e-1],s[e]),d.setLink(s[e-3],s[e-2]);break;case 40:this.$=s[e-1],d.setLink(s[e-1],s[e]);break;case 41:case 47:this.$=s[e-1]+" "+s[e];break;case 42:case 43:case 45:this.$=s[e-2]+" "+s[e-1]+" "+s[e];break;case 44:case 46:this.$=s[e-3]+" "+s[e-2]+" "+s[e-1]+" "+s[e];break}},"anonymous"),table:[{3:1,4:[1,2]},{1:[3]},t(r,[2,2],{5:3}),{6:[1,4],7:5,8:[1,6],9:7,10:[1,8],11:17,12:i,13:n,14:a,15:k,16:T,17:S,18:Y,19:18,20:A,21:D,22:$,23:L,24:W,25:O,26:_,27:J,28:B,29:Q,30:j,31:G,33:Z,35:I,36:p,37:24,38:f,40:u},t(r,[2,7],{1:[2,1]}),t(r,[2,3]),{9:36,11:17,12:i,13:n,14:a,15:k,16:T,17:S,18:Y,19:18,20:A,21:D,22:$,23:L,24:W,25:O,26:_,27:J,28:B,29:Q,30:j,31:G,33:Z,35:I,36:p,37:24,38:f,40:u},t(r,[2,5]),t(r,[2,6]),t(r,[2,17]),t(r,[2,18]),t(r,[2,19]),t(r,[2,20]),t(r,[2,21]),t(r,[2,22]),t(r,[2,23]),t(r,[2,24]),t(r,[2,25]),t(r,[2,26]),t(r,[2,27]),{32:[1,37]},{34:[1,38]},t(r,[2,30]),t(r,[2,31]),t(r,[2,32]),{39:[1,39]},t(r,[2,8]),t(r,[2,9]),t(r,[2,10]),t(r,[2,11]),t(r,[2,12]),t(r,[2,13]),t(r,[2,14]),t(r,[2,15]),t(r,[2,16]),{41:[1,40],43:[1,41]},t(r,[2,4]),t(r,[2,28]),t(r,[2,29]),t(r,[2,33]),t(r,[2,34],{42:[1,42],43:[1,43]}),t(r,[2,40],{41:[1,44]}),t(r,[2,35],{43:[1,45]}),t(r,[2,36]),t(r,[2,38],{42:[1,46]}),t(r,[2,37]),t(r,[2,39])],defaultActions:{},parseError:c(function(o,l){if(l.recoverable)this.trace(o);else{var h=new Error(o);throw h.hash=l,h}},"parseError"),parse:c(function(o){var l=this,h=[0],d=[],b=[null],s=[],F=this.table,e="",x=0,M=0,E=2,C=1,N=s.slice.call(arguments,1),w=Object.create(this.lexer),X={yy:{}};for(var ot in this.yy)Object.prototype.hasOwnProperty.call(this.yy,ot)&&(X.yy[ot]=this.yy[ot]);w.setInput(o,X.yy),X.yy.lexer=w,X.yy.parser=this,typeof w.yylloc>"u"&&(w.yylloc={});var vt=w.yylloc;s.push(vt);var ae=w.options&&w.options.ranges;typeof X.yy.parseError=="function"?this.parseError=X.yy.parseError:this.parseError=Object.getPrototypeOf(this).parseError;function oe(z){h.length=h.length-2*z,b.length=b.length-z,s.length=s.length-z}c(oe,"popStack");function Ot(){var z;return z=d.pop()||w.lex()||C,typeof z!="number"&&(z instanceof Array&&(d=z,z=d.pop()),z=l.symbols_[z]||z),z}c(Ot,"lex");for(var R,tt,H,pt,it={},dt,U,Yt,ft;;){if(tt=h[h.length-1],this.defaultActions[tt]?H=this.defaultActions[tt]:((R===null||typeof R>"u")&&(R=Ot()),H=F[tt]&&F[tt][R]),typeof H>"u"||!H.length||!H[0]){var Tt="";ft=[];for(dt in F[tt])this.terminals_[dt]&&dt>E&&ft.push("'"+this.terminals_[dt]+"'");w.showPosition?Tt="Parse error on line "+(x+1)+`:
`+w.showPosition()+`
Expecting `+ft.join(", ")+", got '"+(this.terminals_[R]||R)+"'":Tt="Parse error on line "+(x+1)+": Unexpected "+(R==C?"end of input":"'"+(this.terminals_[R]||R)+"'"),this.parseError(Tt,{text:w.match,token:this.terminals_[R]||R,line:w.yylineno,loc:vt,expected:ft})}if(H[0]instanceof Array&&H.length>1)throw new Error("Parse Error: multiple actions possible at state: "+tt+", token: "+R);switch(H[0]){case 1:h.push(R),b.push(w.yytext),s.push(w.yylloc),h.push(H[1]),R=null,M=w.yyleng,e=w.yytext,x=w.yylineno,vt=w.yylloc;break;case 2:if(U=this.productions_[H[1]][1],it.$=b[b.length-U],it._$={first_line:s[s.length-(U||1)].first_line,last_line:s[s.length-1].last_line,first_column:s[s.length-(U||1)].first_column,last_column:s[s.length-1].last_column},ae&&(it._$.range=[s[s.length-(U||1)].range[0],s[s.length-1].range[1]]),pt=this.performAction.apply(it,[e,M,x,X.yy,H[1],b,s].concat(N)),typeof pt<"u")return pt;U&&(h=h.slice(0,-1*U*2),b=b.slice(0,-1*U),s=s.slice(0,-1*U)),h.push(this.productions_[H[1]][0]),b.push(it.$),s.push(it._$),Yt=F[h[h.length-2]][h[h.length-1]],h.push(Yt);break;case 3:return!0}}return!0},"parse")},g=function(){var m={EOF:1,parseError:c(function(l,h){if(this.yy.parser)this.yy.parser.parseError(l,h);else throw new Error(l)},"parseError"),setInput:c(function(o,l){return this.yy=l||this.yy||{},this._input=o,this._more=this._backtrack=this.done=!1,this.yylineno=this.yyleng=0,this.yytext=this.matched=this.match="",this.conditionStack=["INITIAL"],this.yylloc={first_line:1,first_column:0,last_line:1,last_column:0},this.options.ranges&&(this.yylloc.range=[0,0]),this.offset=0,this},"setInput"),input:c(function(){var o=this._input[0];this.yytext+=o,this.yyleng++,this.offset++,this.match+=o,this.matched+=o;var l=o.match(/(?:\r\n?|\n).*/g);return l?(this.yylineno++,this.yylloc.last_line++):this.yylloc.last_column++,this.options.ranges&&this.yylloc.range[1]++,this._input=this._input.slice(1),o},"input"),unput:c(function(o){var l=o.length,h=o.split(/(?:\r\n?|\n)/g);this._input=o+this._input,this.yytext=this.yytext.substr(0,this.yytext.length-l),this.offset-=l;var d=this.match.split(/(?:\r\n?|\n)/g);this.match=this.match.substr(0,this.match.length-1),this.matched=this.matched.substr(0,this.matched.length-1),h.length-1&&(this.yylineno-=h.length-1);var b=this.yylloc.range;return this.yylloc={first_line:this.yylloc.first_line,last_line:this.yylineno+1,first_column:this.yylloc.first_column,last_column:h?(h.length===d.length?this.yylloc.first_column:0)+d[d.length-h.length].length-h[0].length:this.yylloc.first_column-l},this.options.ranges&&(this.yylloc.range=[b[0],b[0]+this.yyleng-l]),this.yyleng=this.yytext.length,this},"unput"),more:c(function(){return this._more=!0,this},"more"),reject:c(function(){if(this.options.backtrack_lexer)this._backtrack=!0;else return this.parseError("Lexical error on line "+(this.yylineno+1)+`. You can only invoke reject() in the lexer when the lexer is of the backtracking persuasion (options.backtrack_lexer = true).
`+this.showPosition(),{text:"",token:null,line:this.yylineno});return this},"reject"),less:c(function(o){this.unput(this.match.slice(o))},"less"),pastInput:c(function(){var o=this.matched.substr(0,this.matched.length-this.match.length);return(o.length>20?"...":"")+o.substr(-20).replace(/\n/g,"")},"pastInput"),upcomingInput:c(function(){var o=this.match;return o.length<20&&(o+=this._input.substr(0,20-o.length)),(o.substr(0,20)+(o.length>20?"...":"")).replace(/\n/g,"")},"upcomingInput"),showPosition:c(function(){var o=this.pastInput(),l=new Array(o.length+1).join("-");return o+this.upcomingInput()+`
`+l+"^"},"showPosition"),test_match:c(function(o,l){var h,d,b;if(this.options.backtrack_lexer&&(b={yylineno:this.yylineno,yylloc:{first_line:this.yylloc.first_line,last_line:this.last_line,first_column:this.yylloc.first_column,last_column:this.yylloc.last_column},yytext:this.yytext,match:this.match,matches:this.matches,matched:this.matched,yyleng:this.yyleng,offset:this.offset,_more:this._more,_input:this._input,yy:this.yy,conditionStack:this.conditionStack.slice(0),done:this.done},this.options.ranges&&(b.yylloc.range=this.yylloc.range.slice(0))),d=o[0].match(/(?:\r\n?|\n).*/g),d&&(this.yylineno+=d.length),this.yylloc={first_line:this.yylloc.last_line,last_line:this.yylineno+1,first_column:this.yylloc.last_column,last_column:d?d[d.length-1].length-d[d.length-1].match(/\r?\n?/)[0].length:this.yylloc.last_column+o[0].length},this.yytext+=o[0],this.match+=o[0],this.matches=o,this.yyleng=this.yytext.length,this.options.ranges&&(this.yylloc.range=[this.offset,this.offset+=this.yyleng]),this._more=!1,this._backtrack=!1,this._input=this._input.slice(o[0].length),this.matched+=o[0],h=this.performAction.call(this,this.yy,this,l,this.conditionStack[this.conditionStack.length-1]),this.done&&this._input&&(this.done=!1),h)return h;if(this._backtrack){for(var s in b)this[s]=b[s];return!1}return!1},"test_match"),next:c(function(){if(this.done)return this.EOF;this._input||(this.done=!0);var o,l,h,d;this._more||(this.yytext="",this.match="");for(var b=this._currentRules(),s=0;s<b.length;s++)if(h=this._input.match(this.rules[b[s]]),h&&(!l||h[0].length>l[0].length)){if(l=h,d=s,this.options.backtrack_lexer){if(o=this.test_match(h,b[s]),o!==!1)return o;if(this._backtrack){l=!1;continue}else return!1}else if(!this.options.flex)break}return l?(o=this.test_match(l,b[d]),o!==!1?o:!1):this._input===""?this.EOF:this.parseError("Lexical error on line "+(this.yylineno+1)+`. Unrecognized text.
`+this.showPosition(),{text:"",token:null,line:this.yylineno})},"next"),lex:c(function(){var l=this.next();return l||this.lex()},"lex"),begin:c(function(l){this.conditionStack.push(l)},"begin"),popState:c(function(){var l=this.conditionStack.length-1;return l>0?this.conditionStack.pop():this.conditionStack[0]},"popState"),_currentRules:c(function(){return this.conditionStack.length&&this.conditionStack[this.conditionStack.length-1]?this.conditions[this.conditionStack[this.conditionStack.length-1]].rules:this.conditions.INITIAL.rules},"_currentRules"),topState:c(function(l){return l=this.conditionStack.length-1-Math.abs(l||0),l>=0?this.conditionStack[l]:"INITIAL"},"topState"),pushState:c(function(l){this.begin(l)},"pushState"),stateStackSize:c(function(){return this.conditionStack.length},"stateStackSize"),options:{"case-insensitive":!0},performAction:c(function(l,h,d,b){switch(d){case 0:return this.begin("open_directive"),"open_directive";case 1:return this.begin("acc_title"),31;case 2:return this.popState(),"acc_title_value";case 3:return this.begin("acc_descr"),33;case 4:return this.popState(),"acc_descr_value";case 5:this.begin("acc_descr_multiline");break;case 6:this.popState();break;case 7:return"acc_descr_multiline_value";case 8:break;case 9:break;case 10:break;case 11:return 10;case 12:break;case 13:break;case 14:this.begin("href");break;case 15:this.popState();break;case 16:return 43;case 17:this.begin("callbackname");break;case 18:this.popState();break;case 19:this.popState(),this.begin("callbackargs");break;case 20:return 41;case 21:this.popState();break;case 22:return 42;case 23:this.begin("click");break;case 24:this.popState();break;case 25:return 40;case 26:return 4;case 27:return 22;case 28:return 23;case 29:return 24;case 30:return 25;case 31:return 26;case 32:return 28;case 33:return 27;case 34:return 29;case 35:return 12;case 36:return 13;case 37:return 14;case 38:return 15;case 39:return 16;case 40:return 17;case 41:return 18;case 42:return 20;case 43:return 21;case 44:return"date";case 45:return 30;case 46:return"accDescription";case 47:return 36;case 48:return 38;case 49:return 39;case 50:return":";case 51:return 6;case 52:return"INVALID"}},"anonymous"),rules:[/^(?:%%\{)/i,/^(?:accTitle\s*:\s*)/i,/^(?:(?!\n||)*[^\n]*)/i,/^(?:accDescr\s*:\s*)/i,/^(?:(?!\n||)*[^\n]*)/i,/^(?:accDescr\s*\{\s*)/i,/^(?:[\}])/i,/^(?:[^\}]*)/i,/^(?:%%(?!\{)*[^\n]*)/i,/^(?:[^\}]%%*[^\n]*)/i,/^(?:%%*[^\n]*[\n]*)/i,/^(?:[\n]+)/i,/^(?:\s+)/i,/^(?:%[^\n]*)/i,/^(?:href[\s]+["])/i,/^(?:["])/i,/^(?:[^"]*)/i,/^(?:call[\s]+)/i,/^(?:\([\s]*\))/i,/^(?:\()/i,/^(?:[^(]*)/i,/^(?:\))/i,/^(?:[^)]*)/i,/^(?:click[\s]+)/i,/^(?:[\s\n])/i,/^(?:[^\s\n]*)/i,/^(?:gantt\b)/i,/^(?:dateFormat\s[^#\n;]+)/i,/^(?:inclusiveEndDates\b)/i,/^(?:topAxis\b)/i,/^(?:axisFormat\s[^#\n;]+)/i,/^(?:tickInterval\s[^#\n;]+)/i,/^(?:includes\s[^#\n;]+)/i,/^(?:excludes\s[^#\n;]+)/i,/^(?:todayMarker\s[^\n;]+)/i,/^(?:weekday\s+monday\b)/i,/^(?:weekday\s+tuesday\b)/i,/^(?:weekday\s+wednesday\b)/i,/^(?:weekday\s+thursday\b)/i,/^(?:weekday\s+friday\b)/i,/^(?:weekday\s+saturday\b)/i,/^(?:weekday\s+sunday\b)/i,/^(?:weekend\s+friday\b)/i,/^(?:weekend\s+saturday\b)/i,/^(?:\d\d\d\d-\d\d-\d\d\b)/i,/^(?:title\s[^\n]+)/i,/^(?:accDescription\s[^#\n;]+)/i,/^(?:section\s[^\n]+)/i,/^(?:[^:\n]+)/i,/^(?::[^#\n;]+)/i,/^(?::)/i,/^(?:$)/i,/^(?:.)/i],conditions:{acc_descr_multiline:{rules:[6,7],inclusive:!1},acc_descr:{rules:[4],inclusive:!1},acc_title:{rules:[2],inclusive:!1},callbackargs:{rules:[21,22],inclusive:!1},callbackname:{rules:[18,19,20],inclusive:!1},href:{rules:[15,16],inclusive:!1},click:{rules:[24,25],inclusive:!1},INITIAL:{rules:[0,1,3,5,8,9,10,11,12,13,14,17,23,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52],inclusive:!0}}};return m}();y.lexer=g;function v(){this.yy={}}return c(v,"Parser"),v.prototype=y,y.Parser=v,new v}();xt.parser=xt;var Ve=xt;V.extend(Oe);V.extend($e);V.extend(Le);var Ht={friday:5,saturday:6},q="",St="",Ct=void 0,Et="",ct=[],lt=[],It=new Map,Mt=[],yt=[],at="",At="",Zt=["active","done","crit","milestone","vert"],Ft=[],ut=!1,$t=!1,Lt="sunday",gt="saturday",wt=0,Ne=c(function(){Mt=[],yt=[],at="",Ft=[],mt=0,Dt=void 0,kt=void 0,P=[],q="",St="",At="",Ct=void 0,Et="",ct=[],lt=[],ut=!1,$t=!1,wt=0,It=new Map,Ae(),Lt="sunday",gt="saturday"},"clear"),Re=c(function(t){St=t},"setAxisFormat"),Be=c(function(){return St},"getAxisFormat"),ze=c(function(t){Ct=t},"setTickInterval"),je=c(function(){return Ct},"getTickInterval"),He=c(function(t){Et=t},"setTodayMarker"),qe=c(function(){return Et},"getTodayMarker"),Ge=c(function(t){q=t},"setDateFormat"),Xe=c(function(){ut=!0},"enableInclusiveEndDates"),Ue=c(function(){return ut},"endDatesAreInclusive"),Ke=c(function(){$t=!0},"enableTopAxis"),Je=c(function(){return $t},"topAxisEnabled"),Ze=c(function(t){At=t},"setDisplayMode"),Qe=c(function(){return At},"getDisplayMode"),ts=c(function(){return q},"getDateFormat"),es=c(function(t){ct=t.toLowerCase().split(/[\s,]+/)},"setIncludes"),ss=c(function(){return ct},"getIncludes"),is=c(function(t){lt=t.toLowerCase().split(/[\s,]+/)},"setExcludes"),ns=c(function(){return lt},"getExcludes"),rs=c(function(){return It},"getLinks"),as=c(function(t){at=t,Mt.push(t)},"addSection"),os=c(function(){return Mt},"getSections"),cs=c(function(){let t=qt();const r=10;let i=0;for(;!t&&i<r;)t=qt(),i++;return yt=P,yt},"getTasks"),Qt=c(function(t,r,i,n){const a=t.format(r.trim()),k=t.format("YYYY-MM-DD");return n.includes(a)||n.includes(k)?!1:i.includes("weekends")&&(t.isoWeekday()===Ht[gt]||t.isoWeekday()===Ht[gt]+1)||i.includes(t.format("dddd").toLowerCase())?!0:i.includes(a)||i.includes(k)},"isInvalidDate"),ls=c(function(t){Lt=t},"setWeekday"),us=c(function(){return Lt},"getWeekday"),ds=c(function(t){gt=t},"setWeekend"),te=c(function(t,r,i,n){if(!i.length||t.manualEndTime)return;let a;t.startTime instanceof Date?a=V(t.startTime):a=V(t.startTime,r,!0),a=a.add(1,"d");let k;t.endTime instanceof Date?k=V(t.endTime):k=V(t.endTime,r,!0);const[T,S]=fs(a,k,r,i,n);t.endTime=T.toDate(),t.renderEndTime=S},"checkTaskDates"),fs=c(function(t,r,i,n,a){let k=!1,T=null;for(;t<=r;)k||(T=r.toDate()),k=Qt(t,i,n,a),k&&(r=r.add(1,"d")),t=t.add(1,"d");return[r,T]},"fixTaskDates"),_t=c(function(t,r,i){if(i=i.trim(),c(S=>{const Y=S.trim();return Y==="x"||Y==="X"},"isTimestampFormat")(r)&&/^\d+$/.test(i))return new Date(Number(i));const k=/^after\s+(?<ids>[\d\w- ]+)/.exec(i);if(k!==null){let S=null;for(const A of k.groups.ids.split(" ")){let D=st(A);D!==void 0&&(!S||D.endTime>S.endTime)&&(S=D)}if(S)return S.endTime;const Y=new Date;return Y.setHours(0,0,0,0),Y}let T=V(i,r.trim(),!0);if(T.isValid())return T.toDate();{et.debug("Invalid date:"+i),et.debug("With date format:"+r.trim());const S=new Date(i);if(S===void 0||isNaN(S.getTime())||S.getFullYear()<-1e4||S.getFullYear()>1e4)throw new Error("Invalid date:"+i);return S}},"getStartDate"),ee=c(function(t){const r=/^(\d+(?:\.\d+)?)([Mdhmswy]|ms)$/.exec(t.trim());return r!==null?[Number.parseFloat(r[1]),r[2]]:[NaN,"ms"]},"parseDuration"),se=c(function(t,r,i,n=!1){i=i.trim();const k=/^until\s+(?<ids>[\d\w- ]+)/.exec(i);if(k!==null){let D=null;for(const L of k.groups.ids.split(" ")){let W=st(L);W!==void 0&&(!D||W.startTime<D.startTime)&&(D=W)}if(D)return D.startTime;const $=new Date;return $.setHours(0,0,0,0),$}let T=V(i,r.trim(),!0);if(T.isValid())return n&&(T=T.add(1,"d")),T.toDate();let S=V(t);const[Y,A]=ee(i);if(!Number.isNaN(Y)){const D=S.add(Y,A);D.isValid()&&(S=D)}return S.toDate()},"getEndDate"),mt=0,rt=c(function(t){return t===void 0?(mt=mt+1,"task"+mt):t},"parseId"),hs=c(function(t,r){let i;r.substr(0,1)===":"?i=r.substr(1,r.length):i=r;const n=i.split(","),a={};Wt(n,a,Zt);for(let T=0;T<n.length;T++)n[T]=n[T].trim();let k="";switch(n.length){case 1:a.id=rt(),a.startTime=t.endTime,k=n[0];break;case 2:a.id=rt(),a.startTime=_t(void 0,q,n[0]),k=n[1];break;case 3:a.id=rt(n[0]),a.startTime=_t(void 0,q,n[1]),k=n[2];break}return k&&(a.endTime=se(a.startTime,q,k,ut),a.manualEndTime=V(k,"YYYY-MM-DD",!0).isValid(),te(a,q,lt,ct)),a},"compileData"),ms=c(function(t,r){let i;r.substr(0,1)===":"?i=r.substr(1,r.length):i=r;const n=i.split(","),a={};Wt(n,a,Zt);for(let k=0;k<n.length;k++)n[k]=n[k].trim();switch(n.length){case 1:a.id=rt(),a.startTime={type:"prevTaskEnd",id:t},a.endTime={data:n[0]};break;case 2:a.id=rt(),a.startTime={type:"getStartDate",startData:n[0]},a.endTime={data:n[1]};break;case 3:a.id=rt(n[0]),a.startTime={type:"getStartDate",startData:n[1]},a.endTime={data:n[2]};break}return a},"parseData"),Dt,kt,P=[],ie={},ks=c(function(t,r){const i={section:at,type:at,processed:!1,manualEndTime:!1,renderEndTime:null,raw:{data:r},task:t,classes:[]},n=ms(kt,r);i.raw.startTime=n.startTime,i.raw.endTime=n.endTime,i.id=n.id,i.prevTaskId=kt,i.active=n.active,i.done=n.done,i.crit=n.crit,i.milestone=n.milestone,i.vert=n.vert,i.order=wt,wt++;const a=P.push(i);kt=i.id,ie[i.id]=a-1},"addTask"),st=c(function(t){const r=ie[t];return P[r]},"findTaskById"),ys=c(function(t,r){const i={section:at,type:at,description:t,task:t,classes:[]},n=hs(Dt,r);i.startTime=n.startTime,i.endTime=n.endTime,i.id=n.id,i.active=n.active,i.done=n.done,i.crit=n.crit,i.milestone=n.milestone,i.vert=n.vert,Dt=i,yt.push(i)},"addTaskOrg"),qt=c(function(){const t=c(function(i){const n=P[i];let a="";switch(P[i].raw.startTime.type){case"prevTaskEnd":{const k=st(n.prevTaskId);n.startTime=k.endTime;break}case"getStartDate":a=_t(void 0,q,P[i].raw.startTime.startData),a&&(P[i].startTime=a);break}return P[i].startTime&&(P[i].endTime=se(P[i].startTime,q,P[i].raw.endTime.data,ut),P[i].endTime&&(P[i].processed=!0,P[i].manualEndTime=V(P[i].raw.endTime.data,"YYYY-MM-DD",!0).isValid(),te(P[i],q,lt,ct))),P[i].processed},"compileTask");let r=!0;for(const[i,n]of P.entries())t(i),r=r&&n.processed;return r},"compileTasks"),gs=c(function(t,r){let i=r;nt().securityLevel!=="loose"&&(i=Me(r)),t.split(",").forEach(function(n){st(n)!==void 0&&(re(n,()=>{window.open(i,"_self")}),It.set(n,i))}),ne(t,"clickable")},"setLink"),ne=c(function(t,r){t.split(",").forEach(function(i){let n=st(i);n!==void 0&&n.classes.push(r)})},"setClass"),vs=c(function(t,r,i){if(nt().securityLevel!=="loose"||r===void 0)return;let n=[];if(typeof i=="string"){n=i.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/);for(let k=0;k<n.length;k++){let T=n[k].trim();T.startsWith('"')&&T.endsWith('"')&&(T=T.substr(1,T.length-2)),n[k]=T}}n.length===0&&n.push(t),st(t)!==void 0&&re(t,()=>{Fe.runFunc(r,...n)})},"setClickFun"),re=c(function(t,r){Ft.push(function(){const i=document.querySelector(`[id="${t}"]`);i!==null&&i.addEventListener("click",function(){r()})},function(){const i=document.querySelector(`[id="${t}-text"]`);i!==null&&i.addEventListener("click",function(){r()})})},"pushFun"),ps=c(function(t,r,i){t.split(",").forEach(function(n){vs(n,r,i)}),ne(t,"clickable")},"setClickEvent"),Ts=c(function(t){Ft.forEach(function(r){r(t)})},"bindFunctions"),bs={getConfig:c(()=>nt().gantt,"getConfig"),clear:Ne,setDateFormat:Ge,getDateFormat:ts,enableInclusiveEndDates:Xe,endDatesAreInclusive:Ue,enableTopAxis:Ke,topAxisEnabled:Je,setAxisFormat:Re,getAxisFormat:Be,setTickInterval:ze,getTickInterval:je,setTodayMarker:He,getTodayMarker:qe,setAccTitle:he,getAccTitle:fe,setDiagramTitle:de,getDiagramTitle:ue,setDisplayMode:Ze,getDisplayMode:Qe,setAccDescription:le,getAccDescription:ce,addSection:as,getSections:os,getTasks:cs,addTask:ks,findTaskById:st,addTaskOrg:ys,setIncludes:es,getIncludes:ss,setExcludes:is,getExcludes:ns,setClickEvent:ps,setLink:gs,getLinks:rs,bindFunctions:Ts,parseDuration:ee,isInvalidDate:Qt,setWeekday:ls,getWeekday:us,setWeekend:ds};function Wt(t,r,i){let n=!0;for(;n;)n=!1,i.forEach(function(a){const k="^\\s*"+a+"\\s*$",T=new RegExp(k);t[0].match(T)&&(r[a]=!0,t.shift(1),n=!0)})}c(Wt,"getTaskTags");V.extend(Pe);var xs=c(function(){et.debug("Something is calling, setConf, remove the call")},"setConf"),Gt={monday:Ce,tuesday:Se,wednesday:De,thursday:_e,friday:we,saturday:xe,sunday:be},ws=c((t,r)=>{let i=[...t].map(()=>-1/0),n=[...t].sort((k,T)=>k.startTime-T.startTime||k.order-T.order),a=0;for(const k of n)for(let T=0;T<i.length;T++)if(k.startTime>=i[T]){i[T]=k.endTime,k.order=T+r,T>a&&(a=T);break}return a},"getMaxIntersections"),K,bt=1e4,_s=c(function(t,r,i,n){const a=nt().gantt,k=nt().securityLevel;let T;k==="sandbox"&&(T=ht("#i"+r));const S=k==="sandbox"?ht(T.nodes()[0].contentDocument.body):ht("body"),Y=k==="sandbox"?T.nodes()[0].contentDocument:document,A=Y.getElementById(r);K=A.parentElement.offsetWidth,K===void 0&&(K=1200),a.useWidth!==void 0&&(K=a.useWidth);const D=n.db.getTasks();let $=[];for(const u of D)$.push(u.type);$=f($);const L={};let W=2*a.topPadding;if(n.db.getDisplayMode()==="compact"||a.displayMode==="compact"){const u={};for(const g of D)u[g.section]===void 0?u[g.section]=[g]:u[g.section].push(g);let y=0;for(const g of Object.keys(u)){const v=ws(u[g],y)+1;y+=v,W+=v*(a.barHeight+a.barGap),L[g]=v}}else{W+=D.length*(a.barHeight+a.barGap);for(const u of $)L[u]=D.filter(y=>y.type===u).length}A.setAttribute("viewBox","0 0 "+K+" "+W);const O=S.select(`[id="${r}"]`),_=me().domain([ke(D,function(u){return u.startTime}),ye(D,function(u){return u.endTime})]).rangeRound([0,K-a.leftPadding-a.rightPadding]);function J(u,y){const g=u.startTime,v=y.startTime;let m=0;return g>v?m=1:g<v&&(m=-1),m}c(J,"taskCompare"),D.sort(J),B(D,K,W),ge(O,W,K,a.useMaxWidth),O.append("text").text(n.db.getDiagramTitle()).attr("x",K/2).attr("y",a.titleTopMargin).attr("class","titleText");function B(u,y,g){const v=a.barHeight,m=v+a.barGap,o=a.topPadding,l=a.leftPadding,h=ve().domain([0,$.length]).range(["#00B9FA","#F95002"]).interpolate(pe);j(m,o,l,y,g,u,n.db.getExcludes(),n.db.getIncludes()),Z(l,o,y,g),Q(u,m,o,l,v,h,y),I(m,o),p(l,o,y,g)}c(B,"makeGantt");function Q(u,y,g,v,m,o,l){u.sort((e,x)=>e.vert===x.vert?0:e.vert?1:-1);const d=[...new Set(u.map(e=>e.order))].map(e=>u.find(x=>x.order===e));O.append("g").selectAll("rect").data(d).enter().append("rect").attr("x",0).attr("y",function(e,x){return x=e.order,x*y+g-2}).attr("width",function(){return l-a.rightPadding/2}).attr("height",y).attr("class",function(e){for(const[x,M]of $.entries())if(e.type===M)return"section section"+x%a.numberSectionStyles;return"section section0"}).enter();const b=O.append("g").selectAll("rect").data(u).enter(),s=n.db.getLinks();if(b.append("rect").attr("id",function(e){return e.id}).attr("rx",3).attr("ry",3).attr("x",function(e){return e.milestone?_(e.startTime)+v+.5*(_(e.endTime)-_(e.startTime))-.5*m:_(e.startTime)+v}).attr("y",function(e,x){return x=e.order,e.vert?a.gridLineStartPadding:x*y+g}).attr("width",function(e){return e.milestone?m:e.vert?.08*m:_(e.renderEndTime||e.endTime)-_(e.startTime)}).attr("height",function(e){return e.vert?D.length*(a.barHeight+a.barGap)+a.barHeight*2:m}).attr("transform-origin",function(e,x){return x=e.order,(_(e.startTime)+v+.5*(_(e.endTime)-_(e.startTime))).toString()+"px "+(x*y+g+.5*m).toString()+"px"}).attr("class",function(e){const x="task";let M="";e.classes.length>0&&(M=e.classes.join(" "));let E=0;for(const[N,w]of $.entries())e.type===w&&(E=N%a.numberSectionStyles);let C="";return e.active?e.crit?C+=" activeCrit":C=" active":e.done?e.crit?C=" doneCrit":C=" done":e.crit&&(C+=" crit"),C.length===0&&(C=" task"),e.milestone&&(C=" milestone "+C),e.vert&&(C=" vert "+C),C+=E,C+=" "+M,x+C}),b.append("text").attr("id",function(e){return e.id+"-text"}).text(function(e){return e.task}).attr("font-size",a.fontSize).attr("x",function(e){let x=_(e.startTime),M=_(e.renderEndTime||e.endTime);if(e.milestone&&(x+=.5*(_(e.endTime)-_(e.startTime))-.5*m,M=x+m),e.vert)return _(e.startTime)+v;const E=this.getBBox().width;return E>M-x?M+E+1.5*a.leftPadding>l?x+v-5:M+v+5:(M-x)/2+x+v}).attr("y",function(e,x){return e.vert?a.gridLineStartPadding+D.length*(a.barHeight+a.barGap)+60:(x=e.order,x*y+a.barHeight/2+(a.fontSize/2-2)+g)}).attr("text-height",m).attr("class",function(e){const x=_(e.startTime);let M=_(e.endTime);e.milestone&&(M=x+m);const E=this.getBBox().width;let C="";e.classes.length>0&&(C=e.classes.join(" "));let N=0;for(const[X,ot]of $.entries())e.type===ot&&(N=X%a.numberSectionStyles);let w="";return e.active&&(e.crit?w="activeCritText"+N:w="activeText"+N),e.done?e.crit?w=w+" doneCritText"+N:w=w+" doneText"+N:e.crit&&(w=w+" critText"+N),e.milestone&&(w+=" milestoneText"),e.vert&&(w+=" vertText"),E>M-x?M+E+1.5*a.leftPadding>l?C+" taskTextOutsideLeft taskTextOutside"+N+" "+w:C+" taskTextOutsideRight taskTextOutside"+N+" "+w+" width-"+E:C+" taskText taskText"+N+" "+w+" width-"+E}),nt().securityLevel==="sandbox"){let e;e=ht("#i"+r);const x=e.nodes()[0].contentDocument;b.filter(function(M){return s.has(M.id)}).each(function(M){var E=x.querySelector("#"+M.id),C=x.querySelector("#"+M.id+"-text");const N=E.parentNode;var w=x.createElement("a");w.setAttribute("xlink:href",s.get(M.id)),w.setAttribute("target","_top"),N.appendChild(w),w.appendChild(E),w.appendChild(C)})}}c(Q,"drawRects");function j(u,y,g,v,m,o,l,h){if(l.length===0&&h.length===0)return;let d,b;for(const{startTime:E,endTime:C}of o)(d===void 0||E<d)&&(d=E),(b===void 0||C>b)&&(b=C);if(!d||!b)return;if(V(b).diff(V(d),"year")>5){et.warn("The difference between the min and max time is more than 5 years. This will cause performance issues. Skipping drawing exclude days.");return}const s=n.db.getDateFormat(),F=[];let e=null,x=V(d);for(;x.valueOf()<=b;)n.db.isInvalidDate(x,s,l,h)?e?e.end=x:e={start:x,end:x}:e&&(F.push(e),e=null),x=x.add(1,"d");O.append("g").selectAll("rect").data(F).enter().append("rect").attr("id",E=>"exclude-"+E.start.format("YYYY-MM-DD")).attr("x",E=>_(E.start.startOf("day"))+g).attr("y",a.gridLineStartPadding).attr("width",E=>_(E.end.endOf("day"))-_(E.start.startOf("day"))).attr("height",m-y-a.gridLineStartPadding).attr("transform-origin",function(E,C){return(_(E.start)+g+.5*(_(E.end)-_(E.start))).toString()+"px "+(C*u+.5*m).toString()+"px"}).attr("class","exclude-range")}c(j,"drawExcludeDays");function G(u,y,g,v){if(g<=0||u>y)return 1/0;const m=y-u,o=V.duration({[v??"day"]:g}).asMilliseconds();return o<=0?1/0:Math.ceil(m/o)}c(G,"getEstimatedTickCount");function Z(u,y,g,v){const m=n.db.getDateFormat(),o=n.db.getAxisFormat();let l;o?l=o:m==="D"?l="%d":l=a.axisFormat??"%Y-%m-%d";let h=Te(_).tickSize(-v+y+a.gridLineStartPadding).tickFormat(Pt(l));const b=/^([1-9]\d*)(millisecond|second|minute|hour|day|week|month)$/.exec(n.db.getTickInterval()||a.tickInterval);if(b!==null){const s=parseInt(b[1],10);if(isNaN(s)||s<=0)et.warn(`Invalid tick interval value: "${b[1]}". Skipping custom tick interval.`);else{const F=b[2],e=n.db.getWeekday()||a.weekday,x=_.domain(),M=x[0],E=x[1],C=G(M,E,s,F);if(C>bt)et.warn(`The tick interval "${s}${F}" would generate ${C} ticks, which exceeds the maximum allowed (${bt}). This may indicate an invalid date or time range. Skipping custom tick interval.`);else switch(F){case"millisecond":h.ticks(jt.every(s));break;case"second":h.ticks(zt.every(s));break;case"minute":h.ticks(Bt.every(s));break;case"hour":h.ticks(Rt.every(s));break;case"day":h.ticks(Nt.every(s));break;case"week":h.ticks(Gt[e].every(s));break;case"month":h.ticks(Vt.every(s));break}}}if(O.append("g").attr("class","grid").attr("transform","translate("+u+", "+(v-50)+")").call(h).selectAll("text").style("text-anchor","middle").attr("fill","#000").attr("stroke","none").attr("font-size",10).attr("dy","1em"),n.db.topAxisEnabled()||a.topAxis){let s=Ee(_).tickSize(-v+y+a.gridLineStartPadding).tickFormat(Pt(l));if(b!==null){const F=parseInt(b[1],10);if(isNaN(F)||F<=0)et.warn(`Invalid tick interval value: "${b[1]}". Skipping custom tick interval.`);else{const e=b[2],x=n.db.getWeekday()||a.weekday,M=_.domain(),E=M[0],C=M[1];if(G(E,C,F,e)<=bt)switch(e){case"millisecond":s.ticks(jt.every(F));break;case"second":s.ticks(zt.every(F));break;case"minute":s.ticks(Bt.every(F));break;case"hour":s.ticks(Rt.every(F));break;case"day":s.ticks(Nt.every(F));break;case"week":s.ticks(Gt[x].every(F));break;case"month":s.ticks(Vt.every(F));break}}}O.append("g").attr("class","grid").attr("transform","translate("+u+", "+y+")").call(s).selectAll("text").style("text-anchor","middle").attr("fill","#000").attr("stroke","none").attr("font-size",10)}}c(Z,"makeGrid");function I(u,y){let g=0;const v=Object.keys(L).map(m=>[m,L[m]]);O.append("g").selectAll("text").data(v).enter().append(function(m){const o=m[0].split(Ie.lineBreakRegex),l=-(o.length-1)/2,h=Y.createElementNS("http://www.w3.org/2000/svg","text");h.setAttribute("dy",l+"em");for(const[d,b]of o.entries()){const s=Y.createElementNS("http://www.w3.org/2000/svg","tspan");s.setAttribute("alignment-baseline","central"),s.setAttribute("x","10"),d>0&&s.setAttribute("dy","1em"),s.textContent=b,h.appendChild(s)}return h}).attr("x",10).attr("y",function(m,o){if(o>0)for(let l=0;l<o;l++)return g+=v[o-1][1],m[1]*u/2+g*u+y;else return m[1]*u/2+y}).attr("font-size",a.sectionFontSize).attr("class",function(m){for(const[o,l]of $.entries())if(m[0]===l)return"sectionTitle sectionTitle"+o%a.numberSectionStyles;return"sectionTitle"})}c(I,"vertLabels");function p(u,y,g,v){const m=n.db.getTodayMarker();if(m==="off")return;const o=O.append("g").attr("class","today"),l=new Date,h=o.append("line");h.attr("x1",_(l)+u).attr("x2",_(l)+u).attr("y1",a.titleTopMargin).attr("y2",v-a.titleTopMargin).attr("class","today"),m!==""&&h.attr("style",m.replace(/,/g,";"))}c(p,"drawToday");function f(u){const y={},g=[];for(let v=0,m=u.length;v<m;++v)Object.prototype.hasOwnProperty.call(y,u[v])||(y[u[v]]=!0,g.push(u[v]));return g}c(f,"checkUnique")},"draw"),Ds={setConf:xs,draw:_s},Ss=c(t=>`
  .mermaid-main-font {
        font-family: ${t.fontFamily};
  }

  .exclude-range {
    fill: ${t.excludeBkgColor};
  }

  .section {
    stroke: none;
    opacity: 0.2;
  }

  .section0 {
    fill: ${t.sectionBkgColor};
  }

  .section2 {
    fill: ${t.sectionBkgColor2};
  }

  .section1,
  .section3 {
    fill: ${t.altSectionBkgColor};
    opacity: 0.2;
  }

  .sectionTitle0 {
    fill: ${t.titleColor};
  }

  .sectionTitle1 {
    fill: ${t.titleColor};
  }

  .sectionTitle2 {
    fill: ${t.titleColor};
  }

  .sectionTitle3 {
    fill: ${t.titleColor};
  }

  .sectionTitle {
    text-anchor: start;
    font-family: ${t.fontFamily};
  }


  /* Grid and axis */

  .grid .tick {
    stroke: ${t.gridColor};
    opacity: 0.8;
    shape-rendering: crispEdges;
  }

  .grid .tick text {
    font-family: ${t.fontFamily};
    fill: ${t.textColor};
  }

  .grid path {
    stroke-width: 0;
  }


  /* Today line */

  .today {
    fill: none;
    stroke: ${t.todayLineColor};
    stroke-width: 2px;
  }


  /* Task styling */

  /* Default task */

  .task {
    stroke-width: 2;
  }

  .taskText {
    text-anchor: middle;
    font-family: ${t.fontFamily};
  }

  .taskTextOutsideRight {
    fill: ${t.taskTextDarkColor};
    text-anchor: start;
    font-family: ${t.fontFamily};
  }

  .taskTextOutsideLeft {
    fill: ${t.taskTextDarkColor};
    text-anchor: end;
  }


  /* Special case clickable */

  .task.clickable {
    cursor: pointer;
  }

  .taskText.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }

  .taskTextOutsideLeft.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }

  .taskTextOutsideRight.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }


  /* Specific task settings for the sections*/

  .taskText0,
  .taskText1,
  .taskText2,
  .taskText3 {
    fill: ${t.taskTextColor};
  }

  .task0,
  .task1,
  .task2,
  .task3 {
    fill: ${t.taskBkgColor};
    stroke: ${t.taskBorderColor};
  }

  .taskTextOutside0,
  .taskTextOutside2
  {
    fill: ${t.taskTextOutsideColor};
  }

  .taskTextOutside1,
  .taskTextOutside3 {
    fill: ${t.taskTextOutsideColor};
  }


  /* Active task */

  .active0,
  .active1,
  .active2,
  .active3 {
    fill: ${t.activeTaskBkgColor};
    stroke: ${t.activeTaskBorderColor};
  }

  .activeText0,
  .activeText1,
  .activeText2,
  .activeText3 {
    fill: ${t.taskTextDarkColor} !important;
  }


  /* Completed task */

  .done0,
  .done1,
  .done2,
  .done3 {
    stroke: ${t.doneTaskBorderColor};
    fill: ${t.doneTaskBkgColor};
    stroke-width: 2;
  }

  .doneText0,
  .doneText1,
  .doneText2,
  .doneText3 {
    fill: ${t.taskTextDarkColor} !important;
  }


  /* Tasks on the critical line */

  .crit0,
  .crit1,
  .crit2,
  .crit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.critBkgColor};
    stroke-width: 2;
  }

  .activeCrit0,
  .activeCrit1,
  .activeCrit2,
  .activeCrit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.activeTaskBkgColor};
    stroke-width: 2;
  }

  .doneCrit0,
  .doneCrit1,
  .doneCrit2,
  .doneCrit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.doneTaskBkgColor};
    stroke-width: 2;
    cursor: pointer;
    shape-rendering: crispEdges;
  }

  .milestone {
    transform: rotate(45deg) scale(0.8,0.8);
  }

  .milestoneText {
    font-style: italic;
  }
  .doneCritText0,
  .doneCritText1,
  .doneCritText2,
  .doneCritText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  .vert {
    stroke: ${t.vertLineColor};
  }

  .vertText {
    font-size: 15px;
    text-anchor: middle;
    fill: ${t.vertLineColor} !important;
  }

  .activeCritText0,
  .activeCritText1,
  .activeCritText2,
  .activeCritText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  .titleText {
    text-anchor: middle;
    font-size: 18px;
    fill: ${t.titleColor||t.textColor};
    font-family: ${t.fontFamily};
  }
`,"getStyles"),Cs=Ss,As={parser:Ve,db:bs,renderer:Ds,styles:Cs};export{As as diagram};
