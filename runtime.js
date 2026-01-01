LISTENERS = {}

x = new XMLHttpRequest();
x.open("GET", "http://localhost:8000/", false);
x.send();
user = x.responseText.split(" ")[2].split("<")[0];
// use x.responseText

console.log("Hi from JS!")
document = { querySelectorAll: function(s) {
    var handle = call_python("querySelectorAll", s);
    return handle.map(function(h) { return new Node(h)})
}}

function Node(handle) {this.handle = handle;}

Node.prototype.getAttribute = function(attr) {
    return call_python("getAttribute", this.handle, attr);
}

inputs = document.querySelectorAll('input')
for (var i = 0; i < inputs.length; i++) {
    var name = inputs[i].getAttribute("name");
    var value = inputs[i].getAttribute("value");
    if (value && value.length > 100) {
        console.log("Input " + name + " has too much text.")
    }
}

Node.prototype.addEventListener = function(type, listener) {
    if (!LISTENERS[this.handle]) LISTENERS[this.handle] = {};
    var dict = LISTENERS[this.handle];
    if (!dict[type]) dict[type] = [];
    var list = dict[type];
    list.push(listener);
}

Node.prototype.dispatchEvent = function(evt) {
    var type = evt.type;
    var handle = this.handle;
    var list = (LISTENERS[handle] && LISTENERS[handle][type]) || [];
    for (var i = 0; i < list.length; i++) {
        list[i].call(this, evt);
    }
    return evt.do_default
}

var allow_submit = true;
function lengthCheck() {
    var name = this.getAttribute("name");
    var value = this.getAttribute("value");
    allow_submit = value && value.length <= 100;
    if (!allow_submit) {
        console.log("Input " + name + " has too much text.")
    }
}

var forms = document.querySelectorAll("form");
if (forms.length > 0) {
    var form = forms[0];
    form.addEventListener("submit", function(e) {
        if (!allow_submit) e.preventDefault();
    });
}

var inputs = document.querySelectorAll("input");
for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("keydown", lengthCheck);
}

Object.defineProperty(Node.prototype, 'innerHTML', {
    set: function(s) {
        call_python("innerHTML_set", this.handle, s.toString());
    }
});

function Event(type) {
    this.type = type
    this.do_default = true;
}

Event.prototype.preventDefault = function() {
    this.do_default = false;
}

function XMLHttpRequest() {}

XMLHttpRequest.prototype.open = function(method, url, is_async) {
    if (is_async) throw Error("Only synchronous XHR is supported");
    this.method = method;
    this.url = url;
}

XMLHttpRequest.prototype.send = function(body) {
    this.responseText = call_python("XMLHttpRequest_send", this.method, this.url, body);
}