package dev.boom.subset;

// Development oracle only: does not execute Minecraft or implement guest services.
import java.lang.module.*;
import java.util.*;
import java.util.stream.Collectors;

public final class BootModuleOracle {
    static String internal(String value) { return value.replace('.', '/'); }
    static String quote(String s) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '"' || c == '\\') out.append('\\').append(c);
            else if (c < 32) out.append(String.format("\\u%04x", (int)c));
            else out.append(c);
        }
        return out.append('"').toString();
    }
    static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof String text) return quote(text);
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?,?> map) return map.entrySet().stream().map(e -> quote(e.getKey().toString())+":"+json(e.getValue())).collect(Collectors.joining(",","{","}"));
        if (value instanceof Collection<?> items) return items.stream().map(BootModuleOracle::json).collect(Collectors.joining(",","[","]"));
        throw new IllegalArgumentException(value.getClass().getName());
    }
    static Map<String,Object> record(Object... pairs) {
        Map<String,Object> out = new TreeMap<>();
        for (int i=0;i<pairs.length;i+=2) out.put((String)pairs[i],pairs[i+1]);
        return out;
    }
    static Map<String,Object> descriptor(ModuleDescriptor d) {
        int flags = (d.isOpen()?32:0)
            | (d.modifiers().contains(ModuleDescriptor.Modifier.SYNTHETIC)?4096:0)
            | (d.modifiers().contains(ModuleDescriptor.Modifier.MANDATED)?32768:0);
        List<Object> requires = new ArrayList<>(), exports = new ArrayList<>(), opens = new ArrayList<>(), provides = new ArrayList<>();
        for (var r : d.requires()) {
            int f = (r.modifiers().contains(ModuleDescriptor.Requires.Modifier.TRANSITIVE)?32:0)
                | (r.modifiers().contains(ModuleDescriptor.Requires.Modifier.STATIC)?64:0)
                | (r.modifiers().contains(ModuleDescriptor.Requires.Modifier.SYNTHETIC)?4096:0)
                | (r.modifiers().contains(ModuleDescriptor.Requires.Modifier.MANDATED)?32768:0);
            requires.add(record("module",r.name(),"flags",f,"version",r.compiledVersion().map(Object::toString).orElse(null)));
        }
        for (var e : d.exports()) {
            int f = (e.modifiers().contains(ModuleDescriptor.Exports.Modifier.SYNTHETIC)?4096:0) | (e.modifiers().contains(ModuleDescriptor.Exports.Modifier.MANDATED)?32768:0);
            exports.add(record("package",internal(e.source()),"flags",f,"targets",new TreeSet<>(e.targets())));
        }
        for (var e : d.opens()) {
            int f = (e.modifiers().contains(ModuleDescriptor.Opens.Modifier.SYNTHETIC)?4096:0) | (e.modifiers().contains(ModuleDescriptor.Opens.Modifier.MANDATED)?32768:0);
            opens.add(record("package",internal(e.source()),"flags",f,"targets",new TreeSet<>(e.targets())));
        }
        for (var p : d.provides()) provides.add(record("service",internal(p.service()),"providers",p.providers().stream().map(BootModuleOracle::internal).toList()));
        return record("name",d.name(),"flags",flags,"version",d.rawVersion().orElse(null),"requires",requires,"exports",exports,"opens",opens,"uses",d.uses().stream().map(BootModuleOracle::internal).sorted().toList(),"provides",provides,"packages",d.packages().stream().map(BootModuleOracle::internal).sorted().toList(),"main_class",d.mainClass().map(BootModuleOracle::internal).orElse(null));
    }
    public static void main(String[] args) {
        Map<String,Object> descriptors = new TreeMap<>(), resolved = new TreeMap<>();
        for (var reference : ModuleFinder.ofSystem().findAll()) descriptors.put(reference.descriptor().name(), descriptor(reference.descriptor()));
        var boot = ModuleLayer.boot();
        for (var m : boot.modules()) {
            var loader = m.getClassLoader();
            String kind = loader == null ? "bootstrap" : loader == ClassLoader.getPlatformClassLoader() ? "platform" : "application";
            resolved.put(m.getName(), record("loader",kind,"reads",boot.modules().stream().filter(m::canRead).map(Module::getName).sorted().toList()));
        }
        System.out.println("BOOM_MODULE_ORACLE "+json(record("descriptors",descriptors,"resolved",resolved)));
    }
}
