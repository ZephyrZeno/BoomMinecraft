package dev.boom.nativeimage;

import com.oracle.svm.core.annotate.Substitute;
import com.oracle.svm.core.annotate.TargetClass;
import java.lang.invoke.MethodHandles.Lookup;
import java.util.Collections;
import java.util.Objects;
import java.util.ServiceLoader;
import org.apache.logging.log4j.status.StatusLogger;

/**
 * Native-only compatibility for the hash-pinned Log4j 2.22.1 implementation.
 * Vanilla is compiled on the unnamed application module without a security
 * manager. Keep the explicit loader, lazy iteration and original failure policy.
 * No service instances or logging state are initialized at image build time.
 */
@TargetClass(className = "org.apache.logging.log4j.util.ServiceLoaderUtil")
final class Log4jServices {
    @Substitute
    @SuppressWarnings("removal")
    static <T> Iterable<T> callServiceLoader(
            Lookup lookup, Class<T> serviceType, ClassLoader loader, boolean verbose) {
        try {
            Objects.requireNonNull(lookup);
            if (System.getSecurityManager() != null || lookup.lookupClass().getModule().isNamed()) {
                throw new UnsupportedOperationException(
                        "BoomMinecraft service adapter requires an unnamed module without a security manager");
            }
            return ServiceLoader.load(serviceType, loader);
        } catch (Throwable error) {
            if (verbose) {
                StatusLogger.getLogger().error("Unable to load services for service {}", serviceType, error);
            }
            return Collections.emptyList();
        }
    }
}
