package dev.boom.mirrors;
class ClassFailure { static int failure = 1 / zero(); static int zero() { return 0; } }
