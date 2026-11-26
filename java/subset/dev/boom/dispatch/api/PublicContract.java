package dev.boom.dispatch.api;
interface HiddenDefault {default int f(int n){return n+11;}}
public interface PublicContract extends HiddenDefault {}
